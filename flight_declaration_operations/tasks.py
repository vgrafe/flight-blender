
from flight_blender.celery import app
from scd_operations.opint_helper import DSSOperationalIntentsCreator
from auth_helper.common import get_redis
import json
from dataclasses import asdict
import logging
from datetime import timedelta
from notification_operations.notification_helper import NotificationFactory
from notification_operations.data_definitions import FlightDeclarationUpdateMessage
from conformance_monitoring_operations.conformance_checks_handler import FlightOperationConformanceHelper
from dacite import from_dict
from scd_operations.scd_data_definitions import OperationalIntentStorage, SuccessfulOperationalIntentFlightIDStorage, NotifyPeerUSSPostPayload, OperationalIntentDetailsUSSResponse, OperationalIntentUSSDetails, SubscriptionState
from common.database_operations import BlenderDatabaseReader, BlenderDatabaseWriter
from common.data_definitions import OPERATION_STATES 
import logging
from os import environ as env
import arrow

logger = logging.getLogger('django')
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

@app.task(name='submit_flight_declaration_to_dss_async')
def submit_flight_declaration_to_dss_async(flight_declaration_id:str):
    amqp_connection_url = env.get('AMQP_URL', 0)
    my_dss_opint_creator = DSSOperationalIntentsCreator(flight_declaration_id)   
    my_database_reader = BlenderDatabaseReader()  
    r = get_redis()            
    my_database_writer = BlenderDatabaseWriter()    
    
    start_end_time_validated = my_dss_opint_creator.validate_flight_declaration_start_end_time()
    
    logger.info("Flight Operation Validation status %s"% start_end_time_validated)
    if start_end_time_validated:                    
        if amqp_connection_url:        
            validation_ok_msg = "Flight Operation with ID {operation_id} validated for start and end time, submitting to DSS..".format(operation_id = flight_declaration_id)
            send_operational_update_message.delay(flight_declaration_id =flight_declaration_id , message_text = validation_ok_msg, level = 'info')
        logger.info("Submitting to DSS..")

        opint_submission_result = my_dss_opint_creator.submit_flight_declaration_to_dss()    
         
        if opint_submission_result.status_code == 500:
            logger.error(
                "Error in submitting Flight Declaration to the DSS %s"
                % opint_submission_result.status
            )
            if amqp_connection_url:
                dss_submission_error_msg = "Flight Operation with ID {operation_id} could not be submitted to the DSS, check the Auth server and / or the DSS URL".format(
                    operation_id=flight_declaration_id
                )
                send_operational_update_message.delay(
                    flight_declaration_id=flight_declaration_id,
                    message_text=dss_submission_error_msg,
                    level="error",
                )

        elif opint_submission_result.status_code in [200, 201]:

            logger.info("Successfully submitted Flight Declaration to the DSS %s" % opint_submission_result.status)

            if amqp_connection_url:        
                submission_success_msg = "Flight Operation with ID {operation_id} submitted successfully to the DSS".format(operation_id = flight_declaration_id)
                send_operational_update_message.delay(flight_declaration_id =flight_declaration_id , message_text = submission_success_msg, level = 'info')

            ###### Change via new state check helper               
            fo = my_database_reader.get_flight_declaration_by_id(flight_declaration_id=flight_declaration_id)
            fa = my_database_reader.get_flight_authorization_by_flight_declaration_obj(flight_declaration=fo)

            logger.info("Saving created operational intent details..")            
            created_opint = fa.dss_operational_intent_id
            view_r_bounds = fo.bounds
            operational_intent_full_details = OperationalIntentStorage(bounds=view_r_bounds, start_time=fo.start_datetime.isoformat(), end_time=fo.end_datetime.isoformat(), alt_max=50, alt_min=25, success_response = opint_submission_result.dss_response, operational_intent_details= json.loads(fo.operational_intent))
            # Store flight ID 
            delta = timedelta(seconds =10800)
            flight_opint = 'flight_opint.' + str(flight_declaration_id)
            r.set(flight_opint, json.dumps(asdict(operational_intent_full_details)))
            r.expire(name = flight_opint, time = delta)

            # Store the details of the operational intent reference
            flight_op_int_storage = SuccessfulOperationalIntentFlightIDStorage(operation_id=str(flight_declaration_id), operational_intent_id=created_opint)
            
            opint_flightref = 'opint_flightref.' + created_opint                
            r.set(opint_flightref, json.dumps(asdict(flight_op_int_storage)))
            r.expire(name = opint_flightref, time = delta)                               
            logger.info("Changing operation state..")            
            original_state = fo.state
            accepted_state = OPERATION_STATES[1][0]
            my_conformance_helper = FlightOperationConformanceHelper(flight_declaration_id=flight_declaration_id)
            transition_valid = my_conformance_helper.verify_operation_state_transition(original_state = original_state, new_state= accepted_state, event = 'dss_accepts')
            if transition_valid:
                my_database_writer.update_flight_operation_state(flight_declaration_id=flight_declaration_id, state=accepted_state)                
                logger.info("The state change transition to Accepted state from current state Created is valid..")
                fo.add_state_history_entry(new_state=accepted_state, original_state = original_state,notes="Successfully submitted to the DSS")

            if amqp_connection_url:        
                submission_state_updated_msg = "Flight Operation with ID {operation_id} has a updated state: Accepted. ".format(operation_id = flight_declaration_id)
                send_operational_update_message.delay(flight_declaration_id =flight_declaration_id , message_text = submission_state_updated_msg, level = 'info')

            logger.info("Notifying subscribers..")

            # TODO: Make it async             
            # Notify subscribers of new operational intent 
            subscribers = opint_submission_result.dss_response.subscribers            
            if subscribers:
                for subscriber in subscribers:
                    subscriptions_raw = subscriber['subscriptions']
                    uss_base_url = subscriber['uss_base_url']                    
                    blender_base_url = env.get("BLENDER_FQDN", 0)

                    if uss_base_url != blender_base_url: # There are others who are subscribesd, not just ourselves
                        subscriptions = from_dict(dataclass=SubscriptionState, data = subscriptions_raw)
                        op_int_details = from_dict(dataclass = OperationalIntentUSSDetails, data = json.loads(fo.operational_intent))
                        operational_intent = OperationalIntentDetailsUSSResponse(reference=opint_submission_result.dss_response.operational_intent_reference, details=op_int_details)
                        post_notification_payload = NotifyPeerUSSPostPayload(operational_intent_id=created_opint, operational_intent=operational_intent, subscriptions=subscriptions)
                        # Notify Subscribers
                        my_dss_opint_creator.notify_peer_uss(uss_base_url= uss_base_url, notification_payload=post_notification_payload)


        logger.info("Details of the submission status %s" % opint_submission_result.message)

    else:
        logging.error(
            "Flight Declaration start / end times are not valid, please check the submitted declaration, this operation will not be sent to the DSS for strategic deconfliction"
        )
        if amqp_connection_url:
            validation_not_ok_msg = "Flight Operation with ID {operation_id} did not pass time validation, start and end time may not be ahead of two hours".format(
                operation_id=flight_declaration_id
            )
            send_operational_update_message.delay(
                flight_declaration_id=flight_declaration_id,
                message_text=validation_not_ok_msg,
                level="error",
            )

@app.task(name="send_operational_update_message")
def send_operational_update_message(
    flight_declaration_id: str,
    message_text: str,
    level: str = "info",
    timestamp: str = None,
):
    if not timestamp:
        now = arrow.now()
        timestamp = now.isoformat()

    update_message = FlightDeclarationUpdateMessage(
        body=message_text, level=level, timestamp=timestamp
    )
    amqp_connection_url = env.get("AMQP_URL", 0)
    if amqp_connection_url:
        my_notification_helper = NotificationFactory(
            flight_declaration_id=flight_declaration_id,
            amqp_connection_url=amqp_connection_url,
        )
        my_notification_helper.declare_queue(queue_name=flight_declaration_id)
        my_notification_helper.send_message(message_details=update_message)
        logger.info("Submitted Flight Declaration Notification")
    else:
        logger.info("No AMQP URL specified ")

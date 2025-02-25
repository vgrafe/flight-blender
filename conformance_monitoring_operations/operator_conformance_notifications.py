from flight_declaration_operations.tasks import send_operational_update_message
from dotenv import load_dotenv, find_dotenv
from os import environ as env
import logging
load_dotenv(find_dotenv())


class OperationConformanceNotification():

    def __init__(self, flight_declaration_id:str):
        self.amqp_connection_url = env.get('AMQP_URL', 0)
        self.flight_declaration_id = flight_declaration_id

            
    def send_conformance_status_notification(self, message:str, level:str):        

        if self.amqp_connection_url:                    
            send_operational_update_message.delay(flight_declaration_id =self.flight_declaration_id , message_text = message, level = level)
        else: 
            # If no AMQP is specified then 
            logging.error("Conformance Notification for {operation_id}".format(operation_id = self.flight_declaration_id))
            logging.error(message)


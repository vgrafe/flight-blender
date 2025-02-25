from flight_declaration_operations.models import FlightAuthorization, FlightDeclaration
from conformance_monitoring_operations.models import TaskScheduler
from typing import Tuple, List
from uuid import uuid4
import arrow
from django.db.utils import IntegrityError
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import os
import json
import logging
logger = logging.getLogger('django')
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
 
ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)
    
class BlenderDatabaseReader():
    """
    A file to unify read and write operations to the database. Eventually caching etc. can be added via this file
    """

    def get_all_flight_declarations(self) ->Tuple[None, List[FlightDeclaration]]:        
        
        flight_declarations = FlightDeclaration.objects.all()
        return flight_declarations
        
    def get_flight_declaration_by_id(self, flight_declaration_id:str) ->Tuple[None, FlightDeclaration]:        
        try:
            flight_declaration = FlightDeclaration.objects.get(id = flight_declaration_id)
            return flight_declaration
        except FlightDeclaration.DoesNotExist: 
            return None

    def get_flight_authorization_by_flight_declaration_obj(self, flight_declaration:FlightDeclaration) ->Tuple[None, FlightAuthorization]:        
        try:
            flight_authorization = FlightAuthorization.objects.get(declaration = flight_declaration)
            return flight_authorization
        except FlightDeclaration.DoesNotExist: 
            return None
        except FlightAuthorization.DoesNotExist: 
            return None

    def get_flight_authorization_by_flight_declaration(self, flight_declaration_id:str) ->Tuple[None, FlightAuthorization]:        
        try:
            flight_declaration = FlightDeclaration.objects.get(id = flight_declaration_id)
            flight_authorization = FlightAuthorization.objects.get(declaration = flight_declaration)
            return flight_authorization
        except FlightDeclaration.DoesNotExist: 
            return None
        except FlightAuthorization.DoesNotExist: 
            return None

    def get_current_flight_declaration_ids(self, now:str ) ->Tuple[None, uuid4]:  
        ''' This method gets flight operation ids that are active in the system'''
        n = arrow.get(now)
        
        two_minutes_before_now = n.shift(seconds = -120).isoformat()
        five_hours_from_now = n.shift(minutes = 300).isoformat()    
        relevant_ids =  FlightDeclaration.objects.filter(start_datetime__gte = two_minutes_before_now, end_datetime__lte = five_hours_from_now).values_list('id', flat=True)        
        return relevant_ids
    
    def get_current_flight_accepted_activated_declaration_ids(self, now:str ) ->Tuple[None, uuid4]:  
        ''' This method gets flight operation ids that are active in the system'''
        n = arrow.get(now)
        
        two_minutes_before_now = n.shift(seconds = -120).isoformat()
        five_hours_from_now = n.shift(minutes = 300).isoformat()    
        relevant_ids =  FlightDeclaration.objects.filter(start_datetime__gte = two_minutes_before_now, end_datetime__lte = five_hours_from_now).filter(state__in = [1,2]).values_list('id', flat=True)        
        return relevant_ids

    def get_conformance_monitoring_task(self, flight_declaration: FlightDeclaration) -> Tuple[None, TaskScheduler]:
        try:
            return TaskScheduler.objects.get(flight_declaration = flight_declaration)
        except TaskScheduler.DoesNotExist: 
            return None
        

class BlenderDatabaseWriter():    

    def create_flight_authorization(self, flight_declaration_id:str) ->bool:    
        try:
            flight_declaration = FlightDeclaration.objects.get(id = flight_declaration_id)
            flight_authorization = FlightAuthorization(declaration = flight_declaration)
            flight_authorization.save()
            return True
        except FlightDeclaration.DoesNotExist: 
            return False
        except IntegrityError as ie:
            return False
       
    def update_telemetry_timestamp(self, flight_declaration_id:str) ->bool:        
        now = arrow.now().isoformat()
        try:
            flight_declaration = FlightDeclaration.objects.get(id = flight_declaration_id)
            flight_declaration.latest_telemetry_datetime = now
            flight_declaration.save()
            return True
        except FlightDeclaration.DoesNotExist: 
            return False
        
    def update_flight_authorization_op_int(self, flight_authorization:FlightAuthorization,dss_operational_intent_id) -> bool:
        try: 
            flight_authorization.dss_operational_intent_id = dss_operational_intent_id
            flight_authorization.save()
            return True
        except Exception as e: 
            return False
        
    def update_flight_operation_state(self,flight_declaration_id:str, state:int) -> bool:
        try: 
            flight_declaration = FlightDeclaration.objects.get(id = flight_declaration_id)
            flight_declaration.state = state
            flight_declaration.save()
            return True
        except Exception as e: 
            return False

    def create_conformance_monitoring_periodic_task(self, flight_declaration:FlightDeclaration) -> bool:
        conformance_monitoring_job = TaskScheduler()
        every=int(os.getenv('HEARTBEAT_RATE_SECS', default=5))        
        now = arrow.now()
        fd_end = arrow.get(flight_declaration.end_datetime)        
        delta = fd_end - now
        delta_seconds = delta.total_seconds()
        expires = now.shift(seconds = delta_seconds)                
        task_name = 'check_flight_conformance'
        
        try:
            p_task  = conformance_monitoring_job.schedule_every(task_name= task_name, period='seconds', every = every, expires = expires, flight_declaration= flight_declaration)  
            p_task.start()
            return True
        except Exception as e:             
            logging.error()
            return False

    def remove_conformance_monitoring_periodic_task(self, conformance_monitoring_task:TaskScheduler):
        conformance_monitoring_task.terminate()
        
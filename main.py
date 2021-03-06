#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# calendar string format: 2015-08-26T09:00:00-05:00
# import httplib2
import webapp2
import os
import jinja2
import datetime
import time
import json
import logging
import re
from datetime import datetime, date, time, timedelta

from google.appengine.ext import ndb
from google.appengine.api import users, memcache
from oauth2client.appengine import CredentialsModel
from google.net.proto.ProtocolBuffer import ProtocolBufferDecodeError
from apiclient.discovery import build
from oauth2client.appengine import OAuth2DecoratorFromClientSecrets

logging.getLogger().setLevel(logging.DEBUG)

JINJA_ENVIRONMENT = jinja2.Environment(
    loader = jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions = ['jinja2.ext.autoescape'],
    autoescape = True
    )

def parseEventTimeFromGoogleCalendar(time_string):
    _time = time_string.split('-')
    _time = '-'.join(_time[0:3])

    return datetime.strptime(_time, '%Y-%m-%dT%H:%M:%S')

class List(ndb.Model):
    name = ndb.StringProperty()
    user_email = ndb.StringProperty()
    time_created = ndb.DateTimeProperty(auto_now_add = True)
    on_calendar = ndb.BooleanProperty(default = False)

class Task(ndb.Model):
    name = ndb.StringProperty()
    estimated_finish_time = ndb.TimeProperty()
    due_date = ndb.DateTimeProperty()
    due_date_event_ID = ndb.StringProperty()
    event_ID = ndb.StringProperty(repeated = True)
    list_key = ndb.KeyProperty(kind = List)
    done = ndb.BooleanProperty(default = False)

class Setting(ndb.Model):
    day_start_time = ndb.TimeProperty(required = True)
    day_end_time = ndb.TimeProperty(required = True)
    max_time_per_block = ndb.TimeProperty(required = True)
    break_time = ndb.TimeProperty(required = True)
    user_email = ndb.StringProperty(required = True)

decorator = OAuth2DecoratorFromClientSecrets(
  os.path.join(os.path.dirname(__file__), 'client_secret.json'),
  'https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/userinfo.email')

calendar_service = build('calendar', 'v3')
user_service = build('oauth2', 'v2')


class MainHandler(webapp2.RequestHandler):
    def get(self):
        template_values = {}
        template = JINJA_ENVIRONMENT.get_template('/templates/login.html')
        self.response.write(template.render( template_values ))


class Calendar(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        # Get the authorized Http object created by the decorator.
        http = decorator.http()
        email = user_service.userinfo().get().execute(http=http).get('email')
        #
        # now = datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
        # # Call the service using the authorized Http object.
        # eventsResult = calendar_service.events().list(
        #     calendarId='primary', timeMin=now, maxResults=10
        #     ).execute(http=http)
        # events = eventsResult.get('items', [])
        # if not events:
        #     event_str = "no up coming events"
        # else:
        #     event = events[0]
        #     start = event['start'].get('dateTime', event['start'].get('date'))
        #     event_str = start + event['summary']

        # lists = List.query(List.user_email == email).order(List.time_created).fetch()

        lists = []
        for l in List.query(List.user_email == email).order(List.name).fetch():
            temp = dict()
            temp['name'] = l.name
            temp['key'] = l.key.urlsafe()
            temp['on_calendar'] = l.on_calendar
            temp['tasks'] = []
            for t in  Task.query(Task.list_key == l.key).order(Task.name):
                temp['tasks'].append(t)
            lists.append(temp)

        template_values = {
            'email' : email,
            'lists' : lists
        }

        template = JINJA_ENVIRONMENT.get_template('/templates/calendar.html')
        self.response.write(template.render( template_values ))


class ManageTasks(webapp2.RequestHandler):
    def get(self):
        eft_choices = []
        start_time = datetime.combine(date.today(), time(0,0))
        for i in range(0,47):
            start_time = start_time + timedelta(minutes = 30)
            eft_choices.append(start_time.strftime("%H:%M"))

        try:
            list_key = ndb.Key(urlsafe = self.request.get('list_key'))
            tasks = Task.query(Task.list_key == list_key).order(Task.due_date)
            template = JINJA_ENVIRONMENT.get_template('/templates/manage_tasks.html')
            template_values = {
                'list' : list_key.get(),
                'tasks': tasks.fetch(),
                'eft_choices' : eft_choices
            }
            self.response.write(template.render(template_values))
        except (ProtocolBufferDecodeError, TypeError, jinja2.exceptions.UndefinedError) as e:
            template = JINJA_ENVIRONMENT.get_template('/templates/error.html')
            self.response.write(template.render({}))

class ManageLists(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        email = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        lists = List.query(List.user_email == email).order(List.time_created).fetch()

        template = JINJA_ENVIRONMENT.get_template('/templates/manage_lists.html')
        template_values = {
            'lists' : lists,
            'email' : email
        }
        self.response.write(template.render( template_values ))

class GetAllLists(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        self.response.write("Failed")


class GetCalendarEvent(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        time_min = self.request.get('start')
        time_max = self.request.get('end')

        http = decorator.http()
        # Call the service using the authorized Http object.
        eventsResult = calendar_service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max).execute(http=http)
        events = eventsResult.get('items', [])
        event_list = []
        for event in events:
            event_dict = dict()
            if 'status' in event and event['status'] == 'confirmed':
                if 'summary' in event:
                    event_dict['title'] = event['summary']
                    event_dict['link'] = event['htmlLink']
                if 'start' in event:
                    if 'dateTime' in event['start']:
                        event_dict['start'] = event['start'].get('dateTime')
                        event_dict['end'] = event['end'].get('dateTime')
                    else:
                        event_dict['start'] = event['start'].get('date')
                        event_dict['end'] = event['end'].get('date')
                google_calendar_event_id = event['id']
                event_dict['id'] = google_calendar_event_id

                task_event_id = Task.query(Task.event_ID == google_calendar_event_id).fetch()
                # logging.info('google_calendar_event_id = ' + google_calendar_event_id + ', summary = ' + event['summary'] + ', task_event_id = ' + str(len(task_event_id)))
                if len(task_event_id) > 0:
                    event_dict['is_scheduled'] = 'on'
                    event_dict['done'] = task_event_id[0].done
                    logging.info('done = ' + str(task_event_id[0].done))
                else:
                    event_dict['is_scheduled'] = 'off'


                event_list.append(event_dict)

        obj = dict()
        obj['event_list'] = event_list
        obj['size'] = len(events)
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))


class GetListOffCalendar(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        list_key = ndb.Key(urlsafe = self.request.get('list_key'))
        list = list_key.get()
        list.on_calendar = False
        list.put()

        tasks = Task.query(Task.list_key == list_key).fetch()
        task_list = []
        for task in tasks:
            task_dict = dict()
            task_dict['event_ID'] = task.key.id()
            task_list.append(task_dict)
        obj = dict()
        obj['task_list'] = task_list
        obj['status'] = 'Success'
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))

class Busy:
    break_time = time()

    def __init__(self, start=None, end=None):
        if start is None:
            self.start = datetime.now()
        else:
            self.start = start - timedelta(seconds = 3600 * self.break_time.hour + 60 * self.break_time.minute)
        if end is None:
            self.end = datetime.now()
        else:
            self.end = end + timedelta(seconds = 3600 * self.break_time.hour + 60 * self.break_time.minute)

class ScheduleEvent:
    def __init__(self, start, end, task_id):
        self.start = start
        self.end = end
        self.task_id = task_id
    def toString(self):
        return ('Scheduled ' + self.task_id + ' from ' + self.start.isoformat() + ' to ' + self.end.isoformat())

class Task2Schedule:
    def __init__(self, _due_date, _eft, _id):
        self.due_date = _due_date
        self.eft = _eft
        self.id = _id

    def time_sub(self, b):
        seconds = self.eft.hour * 3600 + self.eft.minute * 60 - b.hour * 3600 - b. minute * 60
        hours = seconds // 3600
        seconds -= hours * 3600
        minutes = seconds // 60
        seconds -= minutes * 60
        return time(hours, minutes, seconds)

class Schedule(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        # Get all google calendar events
        now = datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
        http = decorator.http()
        # Call the service using the authorized Http object.
        eventsResult = calendar_service.events().list(calendarId='primary', timeMin=now).execute(http=http)
        events = eventsResult.get('items', [])
        # Construct a list with all busy events

        # Parameters for schedule
        BusyList = []
        schedule_list = []

        current_user = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        settings = Setting.query(Setting.user_email == current_user).fetch()
        if len(settings) > 0:
            setting = settings[0]
            small = setting.max_time_per_block
            day_start = setting.day_start_time
            day_end = setting.day_end_time
            Busy.break_time = setting.break_time
        else:
            small = time(2, 0, 0)
            day_start = time(8, 0, 0)
            day_end = time(22, 00, 00)
            Busy.break_time = time(0, 30, 00)

        increment = timedelta(seconds=1800)

        # Construct now datetime object

        date_str = self.request.get('date') #12/22/2015
        time_str = self.request.get('time') #00:04:02 GMT-0600 (Central Standard Time)
        time_str = time_str.split(' ')[0]   #00:04:02
        local_now = datetime.strptime(date_str + ' ' + time_str, '%m/%d/%Y %X')

        for event in events:
            # Choose status with confirmed
            if 'status' in event and event['status'] == 'confirmed':
                # Do not choose all day events
                if 'dateTime' in event['start']:
                    b = Busy(parseEventTimeFromGoogleCalendar(event['start'].get('dateTime')),
                        parseEventTimeFromGoogleCalendar(event['end'].get('dateTime')))
                    BusyList.append(b)

        fullcalendar_ids = self.request.get_all('fullcalendar_id')
        # logging.info('fullcalendar_ids = ' + str(fullcalendar_ids))
        for fullcalendar_id in fullcalendar_ids:
            # check if fullcalendar_id is in event_ID, if so it is already scheduled, update the color to pink
            task_event_id = Task.query(Task.event_ID == fullcalendar_id).fetch()
            if len(task_event_id) > 0:
                schedule_dict = dict()
                schedule_dict['status'] = 'is_scheduled'
                logging.info('done = ' + str(task_event_id[0].done))
                schedule_dict['done'] = task_event_id[0].done
                schedule_dict['event_id'] = fullcalendar_id
                schedule_list.append(schedule_dict)

            # else it must be a task key, it is not yet scheduled
            else:
                task = ndb.Key(urlsafe = fullcalendar_id).get()
                task_to_schedule = Task2Schedule(task.due_date, task.estimated_finish_time, 'task')
                # partition the task if it is too long
                partitioned_list = []
                schedule_temp_list = []
                while task_to_schedule.eft > small:
                    partitioned_list.append(Task2Schedule(task_to_schedule.due_date, small, task_to_schedule.id))
                    task_to_schedule = Task2Schedule(task_to_schedule.due_date, task_to_schedule.time_sub(small), task_to_schedule.id)
                # logging.info('task_to_schedule.eft = ' + task_to_schedule.eft.isoformat())
                partitioned_list.append(task_to_schedule)

                for tasks in partitioned_list:
                    # temp schedule for task
                    temp_start = local_now
                    temp_end = temp_start + timedelta(seconds=tasks.eft.hour*3600 + tasks.eft.minute*60)
                    BusyList = sorted(BusyList, key=lambda _busy: _busy.start)
                    if len(BusyList) > 0:
                        for busy in BusyList:
                            # increment temp datetime if conflict
                            # logging.info("busy.start" + busy.start.isoformat())
                            # logging.info("temp_start" + temp_start.isoformat())
                            while busy.start <= temp_start < busy.end \
                                or busy.start < temp_end <= busy.end \
                                or (temp_start <= busy.start and busy.end <= temp_end) \
                                or temp_start.time() < day_start \
                                or temp_end.time() >= day_end \
                                or temp_end.time() < day_start:
                                temp_start += increment
                                # logging.info('increment, temp_start now = ' + temp_start.isoformat())
                                temp_end = temp_start + timedelta(seconds=tasks.eft.hour*3600 + tasks.eft.minute*60)

                    else:
                        while temp_start.time() < day_start \
                            or temp_end.time() >= day_end \
                            or temp_end.time() < day_start:
                            temp_start += increment
                            # logging.info('increment, temp_start now = ' + temp_start.isoformat())
                            temp_end = temp_start + timedelta(seconds=tasks.eft.hour*3600 + tasks.eft.minute*60)

                    # update busylist once new temp is scheduled
                    BusyList.append(Busy(temp_start, temp_end))
                    BusyList = sorted(BusyList, key=lambda _busy: _busy.start)
                    # append result to schedule list
                    schedule_temp = ScheduleEvent(temp_start, temp_end, tasks.id)
                    schedule_temp_list.append(schedule_temp)


                for i, schedule_event in enumerate(schedule_temp_list):
                    schedule_dict = dict()
                    schedule_dict['status'] = 'confirmed'

                    logging.info('schedule_event = ' + schedule_event.toString())
                    schedule_dict['start'] = schedule_event.start.isoformat()
                    schedule_dict['end'] = schedule_event.end.isoformat()

                    schedule_dict['name'] = task.name
                    schedule_dict['done'] = task.done
                    schedule_dict['task_key'] = task.key.urlsafe() + ':' + str(i)
                    schedule_dict['list_key'] = task.list_key.urlsafe()
                    schedule_list.append(schedule_dict)

        obj = dict()
        obj['schedule_list'] = schedule_list
        obj['status'] = 'Success'
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))



class LoadDefaultOnCalendar(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        list_keys = self.request.get_all('list_key')
        task_list = []
        for list_key in list_keys:
            list_key1 = ndb.Key(urlsafe=list_key)
            tasks = Task.query(Task.list_key == list_key1).fetch()
            for task in tasks:
                task_dict = dict()
                task_dict['start'] = task.due_date.isoformat()
                task_dict['title'] = task.name
                task_dict['event_ID'] = task.key.id()
                task_list.append(task_dict)
        obj = dict()
        obj['task_list'] = task_list
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))


class PutListOnCalendar(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        task_list = []
        list_key = ndb.Key(urlsafe = self.request.get('list_key'))
        list = list_key.get()
        tasks = Task.query(Task.list_key == list_key).fetch()
        for task in tasks:
            task_dict = dict()
            task_dict['start'] = task.due_date.isoformat()
            task_dict['title'] = task.name
            task_dict['event_ID'] = task.key.id()
            task_list.append(task_dict)

        obj = dict()
        obj['task_list'] = task_list
        if list.on_calendar == False:
            obj['status'] = 'off_calendar'
        else:
            obj['status'] = 'on_calendar'
        list.on_calendar = True
        list.put()
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))


def post_dict(url, json):
    '''
    Pass the whole dictionary as a json body to the url.
    Make sure to use a new Http object each time for thread safety.
    '''
    # http = httplib2.Http()
    # resp, content = http.request(
    #     uri=url,
    #     method='POST',
    #     headers={'Content-Type': 'application/json; charset=UTF-8'},
    #     body=dumps(json),
    # )

class SaveToGoogleCalendar(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        jsonstring = self.request.body
        jsonobject = json.loads(jsonstring)
        task_list = jsonobject.get('task_list', [])
        http = decorator.http()
        # get timezone from usre's Google Calendar settings
        timezone_response = calendar_service.settings().get(setting='timezone').execute(http=http)
        timezone = timezone_response.get('value', [])
        update_schedule = []
        for task_item in task_list:
            task = None
            if ':' in task_item['fullcalendar_id']:
                # new created event
                task = ndb.Key(urlsafe=task_item['fullcalendar_id'].split(':')[0]).get()
                task_name = task.name
            else:
                # else fullcalendar_id is in task.event_ID, then we need to update event
                task_event_id = Task.query(Task.event_ID == task_item['fullcalendar_id']).fetch()
                task_name = task_event_id[0].name

            # get final start and end time for scheduled blocks
            start = datetime.strptime(task_item['start'], '%Y-%m-%dT%H:%M:%S.%fZ')
            end = datetime.strptime(task_item['end'], '%Y-%m-%dT%H:%M:%S.%fZ')
            logging.info('task_item[end] = ' + task_item['end'])

            data = {
                'end':
                    {
                        'dateTime' : end.isoformat(),
                        'timeZone': timezone
                    },
                'start':
                    {
                        'dateTime' : start.isoformat(), #2015-12-13T10:00:00-05:00
                        'timeZone': timezone
                    },
                'summary': task_name + ' scheduled.'
            }
            data_json = json.dumps(data)
            update_schedule_dict = dict()

            if ':' in task_item['fullcalendar_id']:
                eventsResult = calendar_service.events().insert(calendarId='primary', body= data).execute(http=http)
                logging.info('creating ' + str(task_item['fullcalendar_id']))
                update_schedule_dict['event_id'] = eventsResult['id']
                update_schedule_dict['task_key'] = task_item['fullcalendar_id']
                update_schedule_dict['status'] = 'new_created_schedule'
                if len(task.event_ID) == 0:
                    task.event_ID = [eventsResult['id']]
                else:
                    # task has other scheduled block
                    task.event_ID.append(eventsResult['id'])
                task.put()
            else:
                logging.info('updating ' + str(task_item['fullcalendar_id']))
                eventsResult = calendar_service.events().update(calendarId='primary', eventId=task_item['fullcalendar_id'], body=data).execute(http=http)
                update_schedule_dict['event_id'] = task_item['fullcalendar_id']
                update_schedule_dict['status'] = 'old_schedule'

            update_schedule.append(update_schedule_dict)

        obj = dict()
        obj['update_schedule'] = update_schedule
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))


class SyncGoogleCalendarToList(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        # fetch events from google calendar
        # time_min = '2015-11-01T00:00:00.000Z'
        # time_max = '2015-12-31T00:00:00.000Z'

        http = decorator.http()
        # Call the service using the authorized Http object.
        # eventsResult = calendar_service.events().list(
        #     calendarId='primary', timeMin=time_min, timeMax=time_max).execute(http=http)
        eventsResult = calendar_service.events().list(
            calendarId='primary').execute(http=http)
        events = eventsResult.get('items', [])
        new_lists = []
        for event in events:
            status = ''
            if 'summary' in event:
                list_name = None
                due_time = None
                due_date = None
                task_name = None
                title = event['summary']
                pattern = re.compile("^#([^-$\d]*)")
                m = pattern.search(title)
                if m:
                    list_name = m.group(1).strip()
                    logging.info("list name " + list_name)
                pattern = re.compile("(?<=-)(?:(?!\d*:)([^$]))*")
                m = pattern.search(title)
                if m:
                    task_name = m.group(0).strip()
                    logging.info("task name " + task_name)
                pattern = re.compile("(\s+\d.*)(?=$)")
                m = pattern.search(title)
                if m:
                    due_time = m.group(1).strip()
                    logging.info("due time " + due_time)

                if task_name:
                    if 'start' in event:
                        if 'dateTime' in event['start']:
                            due_date = parseEventTimeFromGoogleCalendar(event['start'].get('dateTime'))
                        else:
                            due_date = datetime.strptime(event['start'].get('date'), '%Y-%m-%d')
                            if due_time:
                                due_time = datetime.strptime(due_time, '%I:%M%p')
                                due_date = due_date.replace(hour=due_time.hour, minute=due_time.minute)
                            else:
                                due_date = due_date.replace(hour = 23, minute = 59)

                    list = List.query(List.name == list_name).fetch()
                    if len(list) or list_name in map(lambda x:x['list_name'], new_lists):
                        # add task to existing list
                        if len(list):
                            new_list_key = list[0].key
                        else:
                            new_list_key = ndb.Key(urlsafe=new_lists[next(index for (index, d) in enumerate(new_lists) if d["list_name"] == list_name)].get('list_key'))

                        tasks = Task.query(ndb.AND(Task.list_key == new_list_key, ndb.OR(Task.name == task_name, Task.due_date_event_ID == event['id']))).fetch()
                        if len(tasks):
                            # existing list and task
                            task = tasks[0]
                            task.name = task_name
                            task.due_date = due_date
                            task.put()
                            status = 'existing list and task'
                        else:
                            # existing list but no existing task
                            new_task = Task()
                            new_task.list_key = new_list_key
                            new_task.name = task_name
                            new_task.due_date = due_date
                            new_task.due_date_event_ID = event['id']
                            new_task.put()
                            status = 'existing list but no existing task'
                    else:
                        # declare new list and also add task
                        new_list_dict = dict()
                        new_list = List()
                        new_list.name = list_name
                        new_list.user_email = user_service.userinfo().get().execute(http = decorator.http()).get('email')
                        new_list.put()

                        new_list_dict['list_name'] = list_name
                        new_list_dict['list_key'] = new_list.key.urlsafe()
                        new_lists.append(new_list_dict)

                        new_task = Task()
                        new_task.list_key = new_list.key
                        new_task.name = task_name
                        new_task.due_date = due_date
                        new_task.due_date_event_ID = event['id']
                        new_task.put()
                        status = 'declare new list and also add task'

        obj = dict()
        obj['new_lists'] = new_lists
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))

class GetTasksFromList(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        current_user = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        list = ndb.Key(urlsafe = self.request.get('list_key')).get()
        list_owner = list.user_email
        if current_user == list_owner:
            task_list = []
            tasks = Task.query(Task.list_key == list.key).fetch()
            for task in tasks:
                task_dict = dict()
                task_dict['task_name'] = task.name
                task_dict['due_date'] = task.due_date.isoformat()
                task_dict['eft'] = task.estimated_finish_time.isoformat()
                task_dict['task_key'] = task.key.urlsafe()
                task_list.append(task_dict)

        obj = dict()
        obj['task_list'] = task_list
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))

class NextItemInList(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        lists = List.query().fetch()
        next_item_list = []
        for list in lists:
            next_item_dict = dict()
            tasks = Task.query(ndb.AND(Task.list_key == list.key, Task.due_date > datetime.now())).order(Task.due_date).fetch()
            for task in tasks:
                if task.done == False:
                    next_item_dict['list_key'] = list.key.urlsafe()
                    next_item_dict['task_name'] = task.name
                    next_item_dict['due_date'] = task.due_date.strftime('%m/%d/%Y %I:%M %p')
                    next_item_list.append(next_item_dict)
                    break

        obj = dict()
        obj['list'] = next_item_list
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))

class DeleteScheduledTasks(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        if self.request.get('task_key'):
            task_key = ndb.Key(urlsafe = self.request.get('task_key'))
            for scheduled in task_key.get().event_ID:
                event = calendar_service.events().get(calendarId='primary', eventId=scheduled).execute(http = decorator.http())
                if not 'error' in event and not event['status'] == 'cancelled':
                    eventsResult = calendar_service.events().delete(calendarId='primary', eventId=scheduled).execute(http = decorator.http())
                    if 'error' in eventsResult:
                        self.response.headers['Content-Type'] = 'text/plain'
                        self.response.write('Failed')
                        return
            # task_key.delete()
            task = task_key.get()
            task.event_ID = []
            task.put()
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Success')
        else:
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Failed')


class TotalTimeForList(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        # list = ndb.Key(urlsafe = self.request.get('list_key')).get()
        lists = List.query().fetch()
        total_seconds_list = []
        for list in lists:
            total_seconds_dict = dict()
            tasks = Task.query(Task.list_key == list.key).fetch()
            total_seconds = 0
            for task in tasks:
                total_seconds += task.estimated_finish_time.hour * 3600 + task.estimated_finish_time.minute * 60

            hours = total_seconds // 3600
            total_seconds -= hours * 3600
            minutes = total_seconds // 60
            if len(str(hours)) == 1:
                total_seconds_dict['hours'] = '0' + str(hours)
            else:
                total_seconds_dict['hours'] = str(hours)
            if len(str(minutes)) == 1:
                total_seconds_dict['minutes'] = '0' + str(minutes)
            else:
                total_seconds_dict['minutes'] = str(minutes)

            total_seconds_dict['task_num'] = str(len(tasks))
            total_seconds_dict['list_key'] = list.key.urlsafe()
            total_seconds_list.append(total_seconds_dict)

        obj = dict()
        obj['list'] = total_seconds_list
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))

class CreateList(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        list_name = self.request.get('list_name')
        lists = List.query(List.name == list_name).fetch()
        if len(lists) > 0:
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Repeated')
            return
        current_user = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        logging.info("Call create")
        if self.request.get('list_key'):
            list_key = ndb.Key(urlsafe = self.request.get('list_key'))
            list_owner = list_key.get().user_email
            if current_user == list_owner:
                list = list_key.get()
                list.name = self.request.get('list_name')
                for task in Task.query(Task.list_key == list_key):
                    logging.info("new task")
                    if task.due_date_event_ID:
                        event = calendar_service.events().get(calendarId='primary', eventId=task.due_date_event_ID).execute(http = decorator.http())
                        event['summary'] = re.sub("#.*-", "# " + list.name + " -", event['summary'])
                        logging.info(event['summary'])
                        eventsResult = calendar_service.events().update(calendarId='primary', eventId=task.due_date_event_ID, body=event).execute(http = decorator.http())
                        if 'error' in eventsResult:
                            self.response.headers['Content-Type'] = 'text/plain'
                            self.response.write('Failed')
                            break
                list.put()

                self.response.headers['Content-Type'] = 'text/plain'
                self.response.write('Edited')
            else:
                self.response.headers['Content-Type'] = 'text/plain'
                self.response.write('Failed')


        else:
            new_list = List()
            new_list.name = self.request.get('list_name')
            new_list.user_email = user_service.userinfo().get().execute(http = decorator.http()).get('email')
            new_list.put()
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write(new_list.key.urlsafe())

class DeleteList(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        if self.request.get('list_key'):
            list_key = ndb.Key(urlsafe = self.request.get('list_key'))
            for task in Task.query(Task.list_key == list_key):
                for scheduled in task.event_ID:
                    event = calendar_service.events().get(calendarId='primary', eventId=scheduled).execute(http = decorator.http())
                    if not 'error' in event and not event['status'] == 'cancelled':
                        eventsResult = calendar_service.events().delete(calendarId='primary', eventId=scheduled).execute(http = decorator.http())
                        if 'error' in eventsResult:
                            self.response.headers['Content-Type'] = 'text/plain'
                            self.response.write('Failed')
                            return
                if self.request.get('delete_calendar') == 'on' and task.due_date_event_ID:
                    event = calendar_service.events().get(calendarId='primary', eventId=task_key.get().due_date_event_ID).execute(http = decorator.http())
                    if not 'error' in event and not event['status'] == 'cancelled':
                        eventsResult = calendar_service.events().delete(calendarId='primary', eventId=task.due_date_event_ID).execute(http = decorator.http())
                        if 'error' in eventsResult:
                            self.response.headers['Content-Type'] = 'text/plain'
                            self.response.write('Failed')
                            return
                task.key.delete()
            list_key.delete()
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Success')
        else:
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Failed')
        # self.redirect('/manage_lists')

class CreateTask(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        current_user = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        list_owner = ndb.Key(urlsafe = self.request.get('list_key')).get().user_email
        timezone_response = calendar_service.settings().get(setting='timezone').execute(http=decorator.http())
        timezone = timezone_response.get('value', [])

        if current_user == list_owner:
            task = None
            if self.request.get('task_key'): # Edit Task
                task_key = ndb.Key(urlsafe = self.request.get('task_key'))
                task = task_key.get()
            else: # Create Task
                task = Task()
                task.list_key = ndb.Key(urlsafe = self.request.get('list_key')).get().key

            task.name = self.request.get('task_name')
            if self.request.get('due_date'):
                task.due_date = datetime.strptime(self.request.get('due_date'), "%m/%d/%Y %I:%M %p")
            else:
                task.due_date = None

            if self.request.get('eft'):
                task.estimated_finish_time = datetime.strptime(self.request.get('eft'), "%H:%M").time()
            else:
                task.estimated_finish_time = None

            eventsResult = None
            if task.due_date_event_ID: # if an event already exist
                event = calendar_service.events().get(calendarId='primary', eventId=task.due_date_event_ID).execute(http = decorator.http())
                if task.due_date:
                    if 'dateTime' in event['start']:
                        # not an all-day event
                        event['summary'] = re.sub("-.*$", "- " + task.name, event['summary'])
                        start_time = parseEventTimeFromGoogleCalendar(event['start']['dateTime'])
                        end_time = parseEventTimeFromGoogleCalendar(event['end']['dateTime'])
                        delta = end_time-start_time
                        event['start']['dateTime'] = task.due_date.isoformat()
                        event['start']['timeZone'] = timezone
                        event['end']['dateTime'] = (task.due_date + delta).isoformat()
                        event['end']['timeZone'] = timezone
                    else:
                        # all-day event
                        event['summary'] = re.sub("-.*$", "- " + task.name + " " + task.due_date.strftime("%I:%M%p"), event['summary'])
                        event['start']['date'] = task.due_date.strftime("%Y-%m-%d")
                        event['start']['timeZone'] = timezone
                        event['end']['date'] = task.due_date.strftime("%Y-%m-%d")
                        event['end']['timeZone'] = timezone

                    eventsResult = calendar_service.events().update(calendarId='primary', eventId=task.due_date_event_ID, body=event).execute(http = decorator.http())

                else: # delete evenet if due date is gone
                    eventsResult = calendar_service.events().delete(calendarId='primary', eventId=task.due_date_event_ID).execute(http = decorator.http())
                    if not 'error' in eventsResult:
                        task.due_date_event_ID = None

                if not 'error' in eventsResult:
                    task.put()
                    self.response.headers['Content-Type'] = 'text/plain'
                    self.response.write('Edited')
                else:
                    self.response.headers['Content-Type'] = 'text/plain'
                    self.response.write('Failed')

            else: # no due_date_event yet
                if task.due_date:
                    data = {
                        'end':
                            {
                                'date' : task.due_date.strftime("%Y-%m-%d"),
                                'timeZone': timezone
                            },
                        'start':
                            {
                                'date' : task.due_date.strftime("%Y-%m-%d"),
                                'timeZone': timezone
                            },
                        'summary': "# " + task.list_key.get().name + " - " + task.name + " " + task.due_date.strftime("%I:%M%p")
                    }
                    eventsResult = calendar_service.events().insert(calendarId='primary', body= data).execute(http = decorator.http())

                if not task.due_date or not 'error' in eventsResult:
                    if eventsResult:
                        task.due_date_event_ID = eventsResult['id']
                    task.put()
                    self.response.headers['Content-Type'] = 'text/plain'
                    if self.request.get('task_key'): # Edit Task
                        self.response.write('Edited')
                    else:
                        self.response.write(task.key.urlsafe())
                else:
                    self.response.headers['Content-Type'] = 'text/plain'
                    self.response.write('Failed')

        else:
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Failed')

class EditTaskDone(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        if self.request.get('task_key'):
            task_key = ndb.Key(urlsafe = self.request.get('task_key'))
            task = task_key.get()
            if self.request.get('done') == 'checked':
                task.done = True
            else:
                task.done = False
            task.put()
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Success')
        else:
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Failed')


class DeleteTask(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        if self.request.get('task_key'):
            task_key = ndb.Key(urlsafe = self.request.get('task_key'))
            for scheduled in task_key.get().event_ID:
                event = calendar_service.events().get(calendarId='primary', eventId=scheduled).execute(http = decorator.http())
                if not 'error' in event and not event['status'] == 'cancelled':
                    eventsResult = calendar_service.events().delete(calendarId='primary', eventId=scheduled).execute(http = decorator.http())
                    if 'error' in eventsResult:
                        self.response.headers['Content-Type'] = 'text/plain'
                        self.response.write('Failed')
                        return
            if self.request.get('delete_calendar') == 'on' and task_key.get().due_date_event_ID:
                event = calendar_service.events().get(calendarId='primary', eventId=task_key.get().due_date_event_ID).execute(http = decorator.http())
                logging.info(event)
                if not 'error' in event and not event['status'] == 'cancelled':
                    eventsResult = calendar_service.events().delete(calendarId='primary', eventId=task_key.get().due_date_event_ID).execute(http = decorator.http())
                    if 'error' in eventsResult:
                        self.response.headers['Content-Type'] = 'text/plain'
                        self.response.write('Failed')
                        return
            task_key.delete()
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Success')
        else:
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Failed')

class Logout(webapp2.RequestHandler):
    def get(self):
        credentials = CredentialsModel.query().fetch
        for credential in credentials:
            logging.info(credential.key.url_safe())
        self.redirect('/')


class Settings(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        current_user = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        settings = Setting.query(Setting.user_email == current_user).fetch()
        eft_choices = []
        start_time = datetime.combine(date.today(), time(0,0))
        for i in range(0,47):
            start_time = start_time + timedelta(minutes = 30)
            eft_choices.append(start_time.strftime("%H:%M"))
        if len(settings) > 0:
            template_values = {
                'eft_choices': eft_choices,
                'setting': settings[0]
                }
            template = JINJA_ENVIRONMENT.get_template('/templates/settings.html')
            self.response.write(template.render( template_values ))
        else:
            template_values = {
                'eft_choices': eft_choices
            }
            template = JINJA_ENVIRONMENT.get_template('/templates/settings.html')
            self.response.write(template.render( template_values ))
    @decorator.oauth_required
    def post(self):
        current_user = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        settings = Setting.query(Setting.user_email == current_user).fetch()

        if len(settings) > 0:
            setting = settings[0]
        else:
            setting = Setting()

        setting.day_start_time = datetime.strptime(self.request.get('day_start_time'), "%H:%M").time()
        setting.day_end_time = datetime.strptime(self.request.get('day_end_time'), "%H:%M").time()
        setting.max_time_per_block = datetime.strptime(self.request.get('max_time_per_block'), "%H:%M").time()
        setting.break_time = datetime.strptime(self.request.get('break_time'), "%H:%M").time()
        setting.user_email = current_user
        setting.put()

        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('Success')


class GetRemainingTime(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        remaining_time_list = []
        past_time = timedelta()
        if self.request.get("task_key"):
            task_key = ndb.Key(urlsafe=self.request.get("task_key"))
            if task_key.get().estimated_finish_time:
                for eventId in task_key.get().event_ID:
                    event = calendar_service.events().get(calendarId='primary', eventId=eventId).execute(http = decorator.http())
                    if event['start']:
                        start_time = parseEventTimeFromGoogleCalendar(event['start']['dateTime'])
                        end_time = parseEventTimeFromGoogleCalendar(event['end']['dateTime'])
                        if end_time < date.today():
                            past_time += end_time-start_time
                remaining_time = timedelta(hours=task_key.get().estimated_finish_time.hour, minutes=task_key.get().estimated_finish_time.minute) - past_time
                remaining_time_dict = dict()
                remaining_time_dict['task_key'] = task_key
                remaining_time_dict['remaining_time'] = (datetime.min + remaining_time).replace(year=1900).strftime("%I:%M")
                remaining_time_list.append(remaining_time_dict)
        elif self.request.get("list_key"):
            list_key = ndb.Key(urlsafe=self.request.get("list_key"))
            for task in Task.query(ndb.AND(Task.list_key == list_key, Task.estimated_finish_time != None)):
                for eventId in task.event_ID:
                    event = calendar_service.events().get(calendarId='primary', eventId=eventId).execute(http = decorator.http())
                    if event['start']:
                        start_time = parseEventTimeFromGoogleCalendar(event['start']['dateTime'])
                        end_time = parseEventTimeFromGoogleCalendar(event['end']['dateTime'])
                        if end_time < datetime.today():
                            past_time += end_time-start_time
                remaining_time = timedelta(hours=task.estimated_finish_time.hour, minutes=task.estimated_finish_time.minute) - past_time
                remaining_time_dict = dict()
                remaining_time_dict['task_key'] = task.key.urlsafe()
                remaining_time_dict['remaining_time'] = (datetime.min + remaining_time).replace(year=1900).strftime("%I:%M")
                remaining_time_list.append(remaining_time_dict)

        obj = dict()
        obj['remaining_time_list'] = remaining_time_list
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/calendar', Calendar),
    ('/manage_lists', ManageLists),
    ('/manage_tasks', ManageTasks),
    ('/settings', Settings),
    ('/logout', Logout),
    ('/api/sync_google_calendar_to_list', SyncGoogleCalendarToList),
    ('/api/get_calendar_event', GetCalendarEvent),
    ('/api/put_list_on_calendar', PutListOnCalendar),
    ('/api/get_list_off_calendar', GetListOffCalendar),
    ('/api/get_tasks_from_list', GetTasksFromList),
    ('/api/load_default_on_calendar', LoadDefaultOnCalendar),
    ('/api/total_time_for_list', TotalTimeForList),
    ('/api/save_to_google_calendar', SaveToGoogleCalendar),
    ('/api/next_item_in_list', NextItemInList),
    ('/api/schedule', Schedule),
    ('/api/delete_scheduled_tasks', DeleteScheduledTasks),
    ('/api/create_list', CreateList),
    ('/api/delete_list', DeleteList),
    ('/api/create_task', CreateTask),
    ('/api/edit_task_done', EditTaskDone),
    ('/api/delete_task', DeleteTask),
    ('/api/get_remaining_time', GetRemainingTime),
    (decorator.callback_path, decorator.callback_handler())
], debug=True)

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
import httplib2
import webapp2
import os
import jinja2
import datetime
import time
import json
import logging
from datetime import datetime, date, time, timedelta

from google.appengine.ext import ndb
from google.appengine.api import users, memcache
from apiclient.discovery import build
from oauth2client.appengine import OAuth2DecoratorFromClientSecrets

logging.getLogger().setLevel(logging.DEBUG)

JINJA_ENVIRONMENT = jinja2.Environment(
    loader = jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions = ['jinja2.ext.autoescape'],
    autoescape = True
    )


class List(ndb.Model):
    name = ndb.StringProperty()
    user_email = ndb.StringProperty()
    time_created = ndb.DateTimeProperty(auto_now_add = True)
    on_calendar = ndb.BooleanProperty(default = False)


class Task(ndb.Model):
    name = ndb.StringProperty()
    estimated_finish_time = ndb.TimeProperty()
    due_date = ndb.DateTimeProperty()
    event_ID = ndb.StringProperty(repeated = True)
    list_key = ndb.KeyProperty(kind = List)
    done = ndb.BooleanProperty(default = False)


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
        for l in List.query(List.user_email == email).fetch():
            temp = dict()
            temp['name'] = l.name
            temp['key'] = l.key.urlsafe()
            temp['on_calendar'] = l.on_calendar
            temp['tasks'] = []
            for t in  Task.query(Task.list_key == l.key):
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

        list_key = ndb.Key(urlsafe = self.request.get('list_key'))
        tasks = Task.query(Task.list_key == list_key).order(Task.due_date)
        template = JINJA_ENVIRONMENT.get_template('/templates/manage_tasks.html')
        template_values = {
            'list' : list_key.get(),
            'tasks': tasks.fetch(),
            'eft_choices' : eft_choices
        }
        self.response.write(template.render(template_values))


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
        # user_info = user_service.userinfo()
        # userinfo = user_service.userinfo().v2().me().get().execute(http = decorator.http())
        # userinfo = user_service.userinfo().get().execute(http = decorator.http())
        # self.response.write()


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

                task_event_id = Task.query(Task.event_ID == google_calendar_event_id).fetch()
                logging.info('google_calendar_event_id = ' + google_calendar_event_id + ', summary = ' + event['summary'] + ', task_event_id = ' + str(len(task_event_id)))
                if len(task_event_id) > 0:
                    event_dict['is_scheduled'] = 'on'
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
    def __init__(self, start, end):
        start_ = start.split('-')
        end_ = end.split('-')
        start_ = '-'.join(start_[0:3])
        end_ = '-'.join(end_[0:3])

        self.start = datetime.strptime(start_, '%Y-%m-%dT%H:%M:%S')
        self.end = datetime.strptime(end_, '%Y-%m-%dT%H:%M:%S')

class Schedule(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        # Get all google calendar events
        now = datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
        http = decorator.http()
        # Call the service using the authorized Http object.
        eventsResult = calendar_service.events().list(
            calendarId='primary', timeMin=now).execute(http=http)
        events = eventsResult.get('items', [])
        # Construct a list with all busy events
        BusyList = []
        schedule_list = []
        for event in events:
            # Choose status with confirmed
            if 'status' in event and event['status'] == 'confirmed':
                # Do not choose all day events
                if 'dateTime' in event['start']:
                    b = Busy(event['start'].get('dateTime'), event['end'].get('dateTime'))
                    BusyList.append(b)

        task_keys = self.request.get_all('task_key')
        for task_key in task_keys:
            task = ndb.Key(urlsafe = task_key).get()
            end = task.due_date
            start = end - timedelta(seconds = task.estimated_finish_time.hour*3600 + task.estimated_finish_time.minute*60)
            conflict = False
            for busy in BusyList:
                if busy.start < start < busy.end or busy.start < end < busy.end:
                    conflict = True
                    break

            schedule_dict = dict()
            if conflict == True:
                # Reschedule
                schedule_dict['status'] = 'conflict'
                print 'Reschedule this event!'
            else:
                schedule_dict['status'] = 'confirmed'
                schedule_dict['start'] = start.isoformat()
                schedule_dict['end'] = end.isoformat()

            schedule_dict['name'] = task.name
            schedule_dict['task_key'] = task_key
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

        for task_item in task_list:
            logging.info("save task!")
            # get final start and end time for scheduled blocks
            task = ndb.Key(urlsafe = task_item['fullcalendar_id']).get()
            start = datetime.strptime(task_item['start'], '%Y-%m-%dT%H:%M:%S.%fZ')
            end = datetime.strptime(task_item['end'], '%Y-%m-%dT%H:%M:%S.%fZ')

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
                'summary': task.name + 'prepare'
            }
            data_json = json.dumps(data)

            task_event_id = Task.query(Task.event_ID == task_item['fullcalendar_id']).fetch()
            # if fullcalendar_id is in task.event_ID, then we need to update event
            if len(task_event_id) > 1:
                eventsResult = calendar_service.events().update(calendarId='primary', eventId=task_event_id[0].event_ID, body=data ).execute(http=http)

            # else create a new event
            else:
                eventsResult = calendar_service.events().insert(calendarId='primary', body=data ).execute(http=http)
                logging.info('len(task.event_ID) = ' + str(len(task.event_ID)))
                if len(task.event_ID) == 0:
                    task.event_ID = [eventsResult['id']]
                else:
                    task.event_ID.append(eventsResult['id'])
                task.put()

        self.response.out.write(json.dumps(jsonobject))




class SyncGoogleCalendarToList(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        # fetch events from google calendar
        time_min = '2015-11-01T00:00:00.000Z'
        time_max = '2015-12-31T00:00:00.000Z'

        http = decorator.http()
        # Call the service using the authorized Http object.
        eventsResult = calendar_service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max).execute(http=http)
        events = eventsResult.get('items', [])
        event_list = []
        for event in events:
            event_dict = dict()
            status = ''
            if 'summary' in event:
                title = event['summary']
                if title[0] == '#':
                    # add to list
                    list_name = title[1:].split('-')[0].strip()
                    if len(title[1:].split('-')) > 1:
                        task_name = title[1:].split('-')[1].split('@')[0].strip()
                        if len(title[1:].split('-')[1].split('@')) > 1:
                            due_date = title[1:].split('-')[1].split('@')[1]

                    if 'start' in event:
                        if 'dateTime' in event['start']:
                            start = event['start'].get('dateTime')
                            # due_date = datetime.strptime(start, '%Y-%m-%dT%H:%M:%S.%fZ')
                            start_ = start.split('-')
                            start_ = '-'.join(start_[0:3])
                            due_date = datetime.strptime(start_, '%Y-%m-%dT%H:%M:%S')
                        else:
                            start = event['start'].get('date')
                            due_date = datetime.strptime(start, '%Y-%m-%d')

                    list = List.query(List.name == list_name).fetch()
                    if len(list):
                        # add task to existing list
                        new_list = list[0]
                        tasks = Task.query(ndb.AND(Task.name == task_name, Task.list_key == new_list.key)).fetch()
                        if len(tasks):
                            # existing list and task
                            task = tasks[0]
                            task.due_date = due_date
                            task.estimated_finish_time = datetime.strptime('03:00', "%H:%M").time()
                            task.put()
                            status = 'existing list and task'
                        else:
                            # existing list but no existing task
                            new_task = Task()
                            new_task.list_key = new_list.key
                            new_task.name = task_name
                            new_task.due_date = due_date
                            new_task.estimated_finish_time = datetime.strptime('03:00', "%H:%M").time()
                            new_task.put()
                            status = 'existing list but no existing task'
                    else:
                        # declare new list and also add task
                        new_list = List()
                        new_list.name = list_name
                        new_list.user_email = user_service.userinfo().get().execute(http = decorator.http()).get('email')
                        new_list.put()

                        new_task = Task()
                        new_task.list_key = new_list.key
                        new_task.name = task_name
                        new_task.due_date = due_date
                        new_task.estimated_finish_time = datetime.strptime('03:00', "%H:%M").time()
                        new_task.put()
                        status = 'declare new list and also add task'

            self.response.headers['Content-Type'] = 'text/plain'
            try:
                self.response.write(start)
            except NameError:
                print "well, it WASN'T defined after all!"
            else:
                self.response.write(task_name + status)
            # if 'start' in event:
            #     if 'dateTime' in event['start']:
            #         event_dict['start'] = event['start'].get('dateTime')
            #         event_dict['end'] = event['end'].get('dateTime')
            #     else:
            #         event_dict['start'] = event['start'].get('date')
            #         event_dict['end'] = event['end'].get('date')


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
            tasks = Task.query(ndb.AND(Task.list_key == list.key, Task.due_date > datetime.now())).order(Task.due_date).fetch(1)
            if tasks:
                next_item_dict['list_key'] = list.key.urlsafe()
                next_item_dict['task_name'] = tasks[0].name
                next_item_dict['due_date'] = tasks[0].due_date.strftime('%m/%d/%Y %I:%M %p')
                next_item_list.append(next_item_dict)

        obj = dict()
        obj['list'] = next_item_list
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))


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
        current_user = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        if self.request.get('list_key'):
            list_key = ndb.Key(urlsafe = self.request.get('list_key'))
            list_owner = list_key.get().user_email
            if current_user == list_owner:
                list = list_key.get()
                list.name = self.request.get('list_name')
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

        if current_user == list_owner:
            if self.request.get('task_key'):
                task_key = ndb.Key(urlsafe = self.request.get('task_key'))
                task = task_key.get()
                task.name = self.request.get('task_name')
                #task.due_date = datetime.strptime(self.request.get('due_date'), '%Y-%m-%dT%H:%M:%S.%fZ')
                task.due_date = datetime.strptime(self.request.get('due_date'), "%m/%d/%Y %I:%M %p")
                task.estimated_finish_time = datetime.strptime(self.request.get('eft'), "%H:%M").time()
                task.put()
                self.response.headers['Content-Type'] = 'text/plain'
                self.response.write('Edited')
            else:
                new_task = Task()
                new_task.list_key = ndb.Key(urlsafe = self.request.get('list_key')).get().key
                new_task.name = self.request.get('task_name')
                new_task.due_date = datetime.strptime(self.request.get('due_date'), "%m/%d/%Y %I:%M %p")
                new_task.estimated_finish_time = datetime.strptime(self.request.get('eft'), "%H:%M").time()
                new_task.put()
                self.response.headers['Content-Type'] = 'text/plain'
                self.response.write(new_task.key.urlsafe())
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
            task_key.delete()
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Success')
        else:
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write('Failed')

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/calendar', Calendar),
    ('/manage_lists', ManageLists),
    ('/manage_tasks', ManageTasks),
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
    ('/api/create_list', CreateList),
    ('/api/delete_list', DeleteList),
    ('/api/create_task', CreateTask),
    ('/api/edit_task_done', EditTaskDone),
    ('/api/delete_task', DeleteTask),
    (decorator.callback_path, decorator.callback_handler())
], debug=True)

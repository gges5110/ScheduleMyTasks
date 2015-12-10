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
import httplib2
import webapp2
import os
import jinja2
import datetime
import json
from datetime import datetime, date, time, timedelta

from google.appengine.ext import ndb
from google.appengine.api import users, memcache
from apiclient.discovery import build
from oauth2client.appengine import OAuth2DecoratorFromClientSecrets

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

        now = datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
        # Call the service using the authorized Http object.
        eventsResult = calendar_service.events().list(
            calendarId='primary', timeMin=now, maxResults=10
            ).execute(http=http)
        events = eventsResult.get('items', [])
        if not events:
            event_str = "no up coming events"
        else:
            event = events[0]
            start = event['start'].get('dateTime', event['start'].get('date'))
            event_str = start + event['summary']

        lists = List.query(List.user_email == email).order(List.time_created).fetch()

        template_values = {
            'event' : event_str,
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
        tasks = Task.query(Task.list_key == list_key)
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
            if 'status' in event and event['status'] == 'cancelled':
                break
            if 'summary' in event:
                event_dict['title'] = event['summary']
            if 'start' in event:
                if 'dateTime' in event['start']:
                    event_dict['start'] = event['start'].get('dateTime')
                    event_dict['end'] = event['end'].get('dateTime')
                else:
                    event_dict['start'] = event['start'].get('date')
                    event_dict['end'] = event['end'].get('date')
            event_list.append(event_dict)

        obj = dict()
        obj['event_list'] = event_list
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))

class GetListOffCalendar(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        list_key = ndb.Key(urlsafe = self.request.get('list_key'))
        list = list_key.get()
        list.on_calendar = False
        list.put()
        obj = dict()
        obj['status'] = 'Success'
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(obj))

class PutListOnCalendar(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        list_key = ndb.Key(urlsafe = self.request.get('list_key'))
        list = list_key.get()
        if list.on_calendar == False:
            list.on_calendar = True
            list.put()
            tasks = Task.query(Task.list_key == list_key).fetch()
            task_list = []
            for task in tasks:
                task_dict = dict()
                task_dict['start'] = task.due_date.isoformat()
                task_dict['title'] = task.name
                task_list.append(task_dict)
            obj = dict()
            obj['task_list'] = task_list
            obj['status'] = 'off_calendar'
            self.response.headers['Content-Type'] = 'application/json'
            self.response.out.write(json.dumps(obj))
        else:
            obj = dict()
            obj['status'] = 'on_calendar'
            self.response.headers['Content-Type'] = 'application/json'
            self.response.out.write(json.dumps(obj))



class CreateList(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        new_list = List()
        new_list.name = self.request.get('list_name')
        new_list.user_email = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        new_list.put()
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(new_list.key.urlsafe())

class CreateTask(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        self.response.headers['Content-Type'] = 'text/plain'
        current_user = user_service.userinfo().get().execute(http = decorator.http()).get('email')

        list_owner = ndb.Key(urlsafe = self.request.get('list_key')).get().user_email
        if current_user == list_owner:
            new_task = Task()
            new_task.list_key = ndb.Key(urlsafe = self.request.get('list_key')).get().key
            new_task.name = self.request.get('task_name')
            new_task.due_date = datetime.strptime(self.request.get('due_date'), "%m/%d/%Y %I:%M %p")
            new_task.estimated_finish_time = datetime.strptime(self.request.get('eft'), "%H:%M").time()
            new_task.put()
            self.response.write(new_task.key.urlsafe())
        else:
            self.response.write('Failed')

class DeleteTask(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        self.response.headers['Content-Type'] = 'text/plain'
        task_key = ndb.Key(urlsafe = self.request.get('task_key'))
        task_key.delete()
        self.response.write('Success')

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/calendar', Calendar),
    ('/manage_lists', ManageLists),
    ('/manage_tasks', ManageTasks),
    ('/api/get_calendar_event', GetCalendarEvent),
    ('/api/put_list_on_calendar', PutListOnCalendar),
    ('/api/get_list_off_calendar', GetListOffCalendar),
    ('/api/create_list', CreateList),
    ('/api/create_task', CreateTask),
    ('/api/delete_task', DeleteTask),
    (decorator.callback_path, decorator.callback_handler())
], debug=True)

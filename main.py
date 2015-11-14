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
from datetime import datetime

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
        
        now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
        # Call the service using the authorized Http object.
        eventsResult = calendar_service.events().list(
            calendarId='primary', timeMin=now, maxResults=10, singleEvents=True,
            orderBy='startTime'
            ).execute(http=http)
        events = eventsResult.get('items', [])
        if not events:
            event_str = "no up coming events"
        else:
            event = events[0]
            start = event['start'].get('dateTime', event['start'].get('date'))
            event_str = start + event['summary']


        template_values = {
            'event' : event_str,
            'email' : email
        }
        template = JINJA_ENVIRONMENT.get_template('/templates/calendar.html')
        self.response.write(template.render( template_values ))   

class ManageLists(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        email = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        lists = []
        for l in List.query(List.user_email == email).fetch():
            temp = dict()
            temp['name'] = l.name
            temp['tasks'] = []
            for t in  Task.query(Task.list_key == l.key):
                temp['tasks'].append(t)
            lists.append(temp)

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
    

class CreateList(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        new_list = List()
        new_list.name = self.request.get('list_name')
        new_list.user_email = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        new_list.put()
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('Success')

class CreateTask(webapp2.RequestHandler):
    @decorator.oauth_required
    def post(self):
        self.response.headers['Content-Type'] = 'text/plain'
        current_user = user_service.userinfo().get().execute(http = decorator.http()).get('email')
        list_owner = ndb.Key(urlsafe = self.request.get('list_key')).get().user_email
        if current_user == list_owner:
            new_task = Task()
            new_task.list_key = self.request.get('list_key')
            new_task.name = self.request.get('task_name')
            new_task.due_date = datetime.strptime(self.request.get('due_date'), "%m/%d/%Y %I:%M %p") 
            new_task.estimated_finish_time = datetime.strptime(self.request.get('eft'), "%H:%M").time()
            self.response.write('Success')
        else:
            self.response.write('Failed')

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/calendar', Calendar),
    ('/manage_lists', ManageLists),
    ('/api/create_lists', CreateList),
    (decorator.callback_path, decorator.callback_handler())
], debug=True)

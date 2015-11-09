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
import webapp2
import os
import jinja2
import datetime
from apiclient.discovery import build
from oauth2client.appengine import OAuth2DecoratorFromClientSecrets

JINJA_ENVIRONMENT = jinja2.Environment(
    loader = jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions = ['jinja2.ext.autoescape'],
    autoescape = True
    )

decorator = OAuth2DecoratorFromClientSecrets(
  os.path.join(os.path.dirname(__file__), 'client_secret.json'),
  'https://www.googleapis.com/auth/calendar.readonly')

service = build('calendar', 'v3')

class MainHandler(webapp2.RequestHandler):
    @decorator.oauth_required
    def get(self):
        # Get the authorized Http object created by the decorator.
        http = decorator.http()
        now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
        # Call the service using the authorized Http object.
        eventsResult = service.events().list(
        calendarId='primary', timeMin=now, maxResults=10, singleEvents=True,
        orderBy='startTime').execute(http=http)
        events = eventsResult.get('items', [])
        if not events:
            event_str = "no up coming events"
        else:
            event = events[0]
            start = event['start'].get('dateTime', event['start'].get('date'))
            event_str = start + event['summary']
        template_values = {
            'event' : event_str
        }
        template = JINJA_ENVIRONMENT.get_template('/templates/login.html')
        self.response.write(template.render( template_values ))        

app = webapp2.WSGIApplication([
    ('/', MainHandler),
    (decorator.callback_path, decorator.callback_handler())
], debug=True)

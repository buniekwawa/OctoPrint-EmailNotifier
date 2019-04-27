# coding=utf-8
from __future__ import absolute_import
import os
import octoprint.plugin
import yagmail
import string

class EmailNotifierPlugin(octoprint.plugin.EventHandlerPlugin,
                          octoprint.plugin.SettingsPlugin,
                          octoprint.plugin.TemplatePlugin):
	
	#~~ SettingsPlugin

	def get_settings_defaults(self):
		# matching password must be registered in system keyring
		# to support customizable mail server, may need port too
		return dict(
			recipient_address="",
			mail_server="",
			mail_username="",
			
			# Notification title and body templates may include any
			# event payload properties associated with the event.
			# http://docs.octoprint.org/en/master/events/index.html#available-events
			# Elapsed times are formatted as H:M:S instead of seconds.
			
			notifications={
				"PrintStarted": dict(
					enabled=True,
					title="Print started {name}",
					body="{name} print started",
					snapshot=False
				),
				"PrintDone": dict(
					enabled=True,
					title="Print complete: {name}",
					body="{name} done in {time}.",
					snapshot=True
				),
				"Progress": dict(
					enabled=True,
					title="Printing progress: {name}",
					body="Printing is at {progress}%",
					snapshot=True,
					step=10
				)
			}
		)
	
	def get_settings_version(self):
		return 2
	
	def on_settings_migrate(self, target, current):
		if current == 1:
			
			# retain smtp/recipient settings
				
			# remove original notification settings
			self._settings.set(["enabled"], None)
			self._settings.set(["include_snapshot"], None)
			self._settings.set(["message_format"], None)
			
			# reset event notifications to new defaults
			self._settings.set(["notifications"], self.get_settings_defaults().get('notifications'))

			self._settings.save()
			
	#~~ TemplatePlugin

	def get_template_configs(self):
		return [
			dict(type="settings", name="Email Notifier", custom_bindings=False)
		]

	#~~ EventPlugin
	
	def on_event(self, event, payload):
		
		# Is there a notification registered for this event?
		notification = self._settings.get(['notifications']).get(event)
		if notification is None:
			return
		
		# Is this notification enabled?
		if not notification.get('enabled', False):
			return
			
		# Convert elapsed times from raw seconds to readable durations.
		if 'time' in payload:
			import datetime
			import octoprint.util
			payload["time"] = octoprint.util.get_formatted_timedelta(datetime.timedelta(seconds=payload["time"]))
		
		# Consider integrating these event subscription properties
		# https://github.com/foosel/OctoPrint/blob/1c6b0554c796f03ed539397daa4b13c44d05a99d/src/octoprint/events.py#L325
		
		# Generate notification message from templates.
		f = ChillFormatter()
		title = f.format(notification.get('title'), **payload)
		content = [f.format(notification.get('body'), **payload)]

		self.send_message(content, title, notification.get('snapshot', False))		

	def on_print_progress(self,location,path,progress):
		notification = self._settings.get(['notifications']).get("Progress")

		if notification is None:
			return
		
		# Is this notification enabled?
		if not notification.get('enabled', False):
			return

		if int(notification.get('step')) == 0 \
			or int(progress) == 0 \
			or int(progress)%int(notification.get('step')) != 0 \
			or int(progress) == 100 :
			return

		tmpDataFromPrinter = self._printer.get_current_data()

		payload['progress']=progress
		
		if tmpDataFromPrinter["job"] is not None and tmpDataFromPrinter["job"]["file"] is not None:
			payload['name']=tmpDataFromPrinter["job"]["file"]["name"]

		f = ChillFormatter()
		title = f.format(notification.get('title'), **payload)
		content = [f.format(notification.get('body'), **payload)]

		self.send_message(content, title, notification.get('snapshot', False))

	def get_update_information(self):
		return dict(
			emailnotifier=dict(
				displayName="EmailNotifier Plugin",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="anoved",
				repo="OctoPrint-EmailNotifier",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/anoved/OctoPrint-EmailNotifier/archive/{target_version}.zip",
				dependency_links=False
			)
		)

	def send_message(self,content, title, includeSnapshot):
		# Should this notification include a webcam snapshot?
		# If so, attempt to attach it to the message content.
		if includeSnapshot:
			snapshot_url = self._settings.globalGet(["webcam", "snapshot"])
			if snapshot_url:
				try:
					import urllib
					snapfile, headers = urllib.urlretrieve(snapshot_url)
				except Exception as e:
					self._logger.exception("Snapshot error (sending email notification without image): %s" % (str(e)))
				else:
					content.append({snapfile: "snapshot.jpg"})
		
		# Send and log.
		try:
			mailer = yagmail.SMTP(user=self._settings.get(['mail_username']), host=self._settings.get(['mail_server']))
			mailer.send(to=self._settings.get(['recipient_address']), subject=title, contents=content, validate_email=False)
		except Exception as e:
			# report problem sending email
			self._logger.exception("Email notification error: %s" % (str(e)))
		else:
			# report notification was sent
			self._logger.info("%s notification sent to %s" % (event, self._settings.get(['recipient_address'])))

# Hack to make .format() chill out about unknown keys. Just let 'em be as-is.
class ChillFormatter(string.Formatter):
	def get_value(self, key, args, kwds):
		if isinstance(key, str):
			return kwds.get(key, '{' + key + '}')
		else:
			Formatter.get_value(key, args, kwds)

__plugin_name__ = "Email Notifier"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = EmailNotifierPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}


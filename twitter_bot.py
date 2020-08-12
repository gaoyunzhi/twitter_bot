#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram_util import log_on_fail, splitCommand, matchKey, autoDestroy, tryDelete, commitRepo
from telegram.ext import Updater, MessageHandler, Filters
import yaml
from db import DB
import threading
from stream import Stream, shouldProcess
import tweepy
import twitter_2_album
import album_sender

db = DB()

with open('CREDENTIALS') as f:
	credential = yaml.load(f, Loader=yaml.FullLoader)

tele = Updater(credential['bot'], use_context=True)  # @twitter_send_bot
debug_group = tele.bot.get_chat(420074357)

HELP_MESSAGE = '''
Subscribe Twitter posts.

commands:
/tw_subscribe user_link/user_id/keywords
/tw_unsubscribe user_link/user_id/keywords
/tw_view - view current subscription

Can be used in group/channel also.

Github： https://github.com/gaoyunzhi/twitter_bot
'''

auth = tweepy.OAuthHandler(credential['twitter_consumer_key'], credential['twitter_consumer_secret'])
auth.set_access_token(credential['twitter_access_token'], credential['twitter_access_secret'])
twitterApi = tweepy.API(auth)

twitter_stream = Stream(db, twitterApi, tele.bot)

def getRetweetedId(status):
	return status._json.get('retweeted_status', {}).get('id')

@log_on_fail(debug_group)
def searchKeys():
	for key in list(db.sub.keys()):
		for status in twitterApi.search(key):
			if 'id' not in status._json or not shouldProcess(status._json, db):
				continue
			if not db.existing.add(status.id):
				continue
			rid = getRetweetedId(status)
			if rid and not db.existing.add(rid):
				continue
			album = twitter_2_album.get(str(status.id))
			for chat_id in db.sub.key_sub.copy():
				if (key not in db.sub.key_sub[chat_id] and 
					not matchKey(album.cap, db.sub.key_sub[chat_id])):
					continue
				try:	
					channel = tele.bot.get_chat(chat_id)	
					album_sender.send_v2(channel, album)
				except Exception as e:
					print('send fail for key', chat_id, str(e))	
					continue

def twitterLoop():
	try:
		twitter_stream.reload()
		db.reload()
	except Exception as e:
		debug_group.send_message('twitter_stream reload error ' + str(e))
	searchKeys()
	print('twitterLoop')
	threading.Timer(10 * 60, twitterLoop).start()

def handleAdmin(command, text):
	if not text:
		return
	success = False
	if command == '/abl':
		db.bocklist.add(text)
		success = True
	if command == '/apl':
		db.popularlist.add(text)
		success = True
	if success:
		autoDestroy(msg.reply_text('success'), 0.1)
		tryDelete(msg)
		commitRepo(delay_minute=0)

@log_on_fail(debug_group)
def handleCommand(update, context):
	msg = update.effective_message
	command, text = splitCommand(msg.text)
	if msg.chat.username in ['b4cxb', 'weibo_read', 'weibo_one']:
		handleAdmin(command, text)
	if not msg or not msg.text.startswith('/tw'):
		return
	success = False
	if 'unsub' in command:
		db.sub.remove(msg.chat_id, text, twitterApi)
		twitter_stream.forceReload()
		success = True
	elif 'sub' in command:
		db.sub.add(msg.chat_id, text, twitterApi)
		twitter_stream.forceReload()
		success = True
	r = msg.reply_text(db.sub.get(msg.chat_id, twitterApi), 
		parse_mode='markdown', disable_web_page_preview=True)
	if msg.chat_id < 0:
		tryDelete(msg)
		if success:
			autoDestroy(r, 0.1)

def handleHelp(update, context):
	update.message.reply_text(HELP_MESSAGE)

def handleStart(update, context):
	if 'start' in update.message.text:
		update.message.reply_text(HELP_MESSAGE)

if __name__ == '__main__':
	searchKeys()
	twitter_stream.forceReload()
	threading.Timer(10 * 60, twitterLoop).start() 
	dp = tele.dispatcher
	dp.add_handler(MessageHandler(Filters.command, handleCommand))
	dp.add_handler(MessageHandler(Filters.private & (~Filters.command), handleHelp))
	dp.add_handler(MessageHandler(Filters.private & Filters.command, handleStart), group=2)
	tele.start_polling()
# 	tele.idle()
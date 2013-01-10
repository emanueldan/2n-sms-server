#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Full featured HTTP SMS server for 2n VoiceBlue GSM VoIP adapters with sending and receivig capabilities.
The server periodically checks the incoming SMS-es on the VoiceBlue adapter then stores in a local SQLite database.
It communicates via /dev/ttyUSBx port with AT commands.
The server also listens on a defined HTTP port and controllable via POST/GET calls. (In case of GET call the message shpold be URL encoded.)   
The HTTP responses are simple XMLs for easy to use and parse.
For details, control functions, output XML templates, please read the README document.
There are a basic WEB frontend available at my project page for this server.

Original manual of VoiceBlue modem:
http://www.2n.cz/download/3/4/2NR_VoiceBlue_-_User_Manual.pdf

DEPENDENCIES:
- Python 2.7.x
- Python-Messaging https://github.com/pmarti/python-messaging
- Python-serial 2.5 > http://sourceforge.net/projects/pyserial/files/pyserial/2.5/pyserial-2.5.tar.gz/download

BASIC USAGE EXAMPLE:
0.) edit config variables below (# CONFIG START section) only if necessary
1.) start HTTP server on port: ./[program name] [server port] (default:8080) as root user!
2.) sending SMS: use a HTTP browser to call the server via GET method: 
	http://[host address:port]/?rcpt=[full tel. number of recipient]&msg=urlencode([155 character sms])&smsc=[our telco's sms center full number (with + and country code, eg: +36...)]
3.) receiving SMS messages: http://[host address:port]/?action=listall

Licensed under GPL v2: http://www.gnu.org/licenses/gpl-2.0.html 
"""

################################
# CONFIG START
################################
SIMCARDSINUSE=[0,1,2,3] 					# maximum card number: 0,1,2,3 so four, if you just use #0, put: CARDSINUSE=[0], etc...
SQLITE_PATH = "/var/lib/2nsmsdb/sms.db" 	# for store incoming, outgoing smses use SQLite lightweight database
LOGFILE = "/var/log/2nsms.log" 				# logfile where the process will be log everything
SERPORT = "/dev/ttyUSB"						# serial USB base location, the program will try open from ttyUSB0 to ttyUSB10
SERBAUD = 921600 							# serial baud rate for 2n USB modem
PORT=str(8080) 								# the default local HTTP port where the server will listen to if not given by startup parameter
SMSC="+36209300099" 						# put here your default telco's SMS center's number, this would be the default if not given in HTTP request (default by the author: Telenor Hungary)
SIMPOLLINTERVAL=15							#poll SIM cards for new messages every given seconds
################################
# CONFIG END
# DO NOT EDIT BELOW CODE JUST IF 
# YOU KNOW WHAT YOU DO!
################################


# import standard libraries
from datetime import datetime
import sys
from time import sleep,strftime,strptime,ctime,localtime,time,mktime,gmtime
from SocketServer import ThreadingMixIn
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import cgi
import logging
from string import split,strip
from threading import Thread
import Queue
import unicodedata
import os
import sqlite3
import hashlib
import signal


#global info
__version__ = "2.02"
__all__ = ["Log","initSQLite","SQLiteClose","SQLiteExec","SQLiteQuery","phoneNumFormatter","USBSerialHandler","SMSRequestHandler","ThreadingHTTPServer"]
__author__ = "Tamas TOBI <tamas.tobi@gmail.com>, Hungary"
__copyright__ = "Copyright (C) Tamas Tobi 2012, License: GPL v2, http://www.gnu.org/licenses/gpl-2.0.html"

#######################################################
## global variables, DO NOT modify them!!!!
#######################################################
SMSLENGTH=155 #normally the max is 160, we use a bit lower safely
USAGE = "Server starting: [program] [port number], Sending usage: http://[host address:port]/?rcpt=[tel. number of recipient]&msg=[155 character sms]&smsc=[our telco's sms center number], Receinig usage: http://[host address:port]/?action=listall"
NEND=True
NL='\r\n'
INQ=Queue.Queue() #input queue for sms sending (http -> serial)

###########################
## configure logging
###########################
logging.basicConfig(level=logging.DEBUG,
					format='%(asctime)s	%(message)s',
					filename=LOGFILE,
					filemode='a'
)

#import 3rd party modules:
try:
	from messaging.sms import SmsSubmit,SmsDeliver
	import serial
except Exception,e:
	Log("Cannot import 3rd party modules, sysexit. ",e)
	NEND=False
	sys.exit(1)

###############################
#check CLI arguments
###############################
try:
	PORT=str(sys.argv[1])
except:
	print "Deafult PORT: ",str(PORT)
	
if PORT == "--help" or PORT == "-h":
	print USAGE
	sys.exit(1)

###############################
## common functions definitions
###############################
def Log(logmsg,ex="",p=True):
	logmsg=str(logmsg)
	if (p):
		try:
			print "Log: %s %s %s %s" % (ctime(), "\t", logmsg, str(ex))
		except:
			pass
	try:
		if len(str(ex)) > 0:
			logging.debug(logmsg+", "+str(ex))
		else:
			logging.debug(logmsg)
	except Exception, e:
		try:
			print logmsg, str(ex), "Log Exception:",str(e)
		except:
			pass

def initSQLite(needobj=None):
	try:
		conn = sqlite3.connect(SQLITE_PATH)
		c = conn.cursor()
		qry='''
		CREATE TABLE IF NOT EXISTS sms 
		(
			smsdate TEXT, 							/* date when the SMS sent/received */
			lastdate TEXT, 							/* date when the row modified last*/
			cardnum INTEGER DEFAULT 32, 			/* number of device's SIM card, when sent: 32, received: 0-4 */
			fromnum TEXT,							/* sender mobile phone number, in case of sending it is empty */
			deleted TEXT,							/* deleted [no, yes] */
			tonum TEXT,								/* recipient  mobile phone number, in case of receiving it is empty*/
			hash TEXT,								/* unique hash of the message */
			msg TEXT,								/* the message body of the sms itself */
			status TEXT								/* status [ queued, sent , senderror, received ] */
		)
		'''
		if not needobj:
			c.execute(qry)
			conn.commit()
			s=c.execute("pragma table_info(sms)")
			rs=c.fetchall()
			Log("initSQLite table INFO: "+str(rs))
	except Exception,e:
		Log('initSQLite: exception: ',e)
		return False
	if needobj:
		return [c,conn]
	else:
		SQLiteClose([c,conn])
		return True

def SQLiteClose(sqlobj):
	try:
		sqlobj[0].close()
	except:
		pass
	try:
		sqlobj[1].close()
	except:
		pass
	return None

def SQLiteExec(qry,sqlobj):
	rtrn=True
	try:
		sqlobj[0].execute(qry)
		if "INSERT" in qry or "insert" in qry:
			rtrn = sqlobj[0].lastrowid
		else:
			rtrn = sqlobj[0].rowcount
		sqlobj[1].commit()
		return rtrn
	except Exception,e:
		Log("SQLiteExec exception: "+str(qry),e)
		return -1

def SQLiteQuery(qry,sqlobj,justone=None):
	try:
		sqlobj[0].execute(qry)
		if justone:
			return sqlobj[0].fetchone()
		else:
			return sqlobj[0].fetchall()
	except Exception,e:
		Log("SQLiteQuery exception: "+str(qry),e)
		if justone:
			return -1
		else:
			return []

def phoneNumFormatter(inp):
	v='0123456789'
	o=''
	inp=str(inp).strip()
	inp=inp.replace("'","")
	inp=inp.replace('"',"")
	inp=inp.replace(' ',"")
	if inp[-2:] == '.0':
		inp=inp[0:-2]
	for i in inp:
		if i in v:
			o+=i
	return str(o)


###############################
## Class definitions
###############################
class USBSerialHandler():
	def __init__(self):
		self.serialport=None
		self.serialportpath=None
		self.initSerialPort()
		Thread(None,self.SerialControllerThread,None,()).start()

	def initSerialPort(self):
		ser = serial.Serial()
		for portnum in xrange(11):
			port=str(portnum)
			Log("initSerialPort try open: "+SERPORT+port)
			try:
				self.serialport.close()
			except:
				pass
			try:
				ser.port=SERPORT+port
				ser.baudrate=SERBAUD
				ser.bytesize=8
				ser.parity='N'
				ser.stopbits=1
				ser.rtscts=0
				ser.timeout = 0
				ser.open()
				if not ser.isOpen():
					Log("initSerialPort: Cannot open serial terminal! Continue...")
					sleep(0.1)
					try:
						ser.close()
					except:
						pass
					continue
				else:
					Log("initSerialPort: "+SERPORT+port+" opened OK.")
					self.serialportpath=SERPORT+port
					self.serialport=ser
					return True
			except Exception,e:
				try:
					ser.close()
				except:
					pass
				Log("initSerialPort Exception: ",e)
				sleep(0.1)
				continue
		if not self.serialportpath:
			Log("initSerialPort: Cannot find usable serial port. Return False.")
			return False

	def CommandSender(self,tosend=None,debug=None,needval=None,assertval='',waitsec=1):
		if not self.serialport:
			self.initSerialPort()
		if self.serialport:
			if not self.serialport.isOpen():
				self.initSerialPort()
		result=None
		if tosend:
			if debug:
				Log("CommandSender tosend: "+str(tosend))
			self.sendCommand("AT",False,needval,'OK',waitsec)
			self.sendCommand("AT!G=55",False,needval,'OK',waitsec)
			self.sendCommand("AT!G=A6",False,needval,'OK',waitsec)
			result=self.sendCommand(tosend,debug,needval,assertval,waitsec)
			self.sendCommand("AT!G=55",False,needval,'OK',waitsec)
		if result:
			if needval:
				return result
			else:
				return True
		else:
			return False

	def readSerial(self,debug=None,needval=None,assertval='',waitsec=1):
		buffer = ''
		z=0
		while NEND:
			r=self.serialport.read(1024)
			if debug:
				print str(z)+": readSerial debug: "+str(r)
			buffer += r
			if "smserr" in buffer:
				Log("readSerial buffer (while) SMS ERROR: "+str(buffer))
				return False
			if assertval in buffer and buffer[-2:] == NL and not debug:
				### Log("readSerial buffer asserted (while): "+str(buffer))
				if needval:
					return buffer
				else:
					return True
			if z >= waitsec*10:
				break
			z+=1
			sleep(0.1)
		if len(buffer):
			if assertval in buffer and buffer[-2:] == NL and not debug:
				Log("readSerial buffer: "+str(buffer))
				if needval:
					return buffer
				else:
					return True
		else:
			Log("readSerial buffer was empty.")
			if needval:
				return buffer
			else:
				return False

	def sendCommand(self,cmd,debug=None,needval=None,assertval='',waitsec=1):
		if debug:
			print "sendCommand debug: "+cmd
		try:
			self.serialport.timeout = 0
			self.serialport.write(cmd)
			self.serialport.flushOutput()
			self.serialport.write(NL)
			self.serialport.flushOutput()
			self.serialport.timeout = 0
			result=self.readSerial(debug,needval,assertval,waitsec)
			return result
		except Exception,e:
			Log("sendCommand Exception:",e)
			return False

	def createSMS(self,num,msg,smsc,shahash):
		num=str(strip(num))
		msg=str(strip(msg))
		smsc=str(strip(smsc))
		
		### Log('createSMS new msg (0): NUM: '+num+", MSG: "+msg+", SMSC: "+smsc+", LEN:"+str(len(msg))+", HASH: "+shahash)
		if smsc[0] != "+" and smsc[0] != "0":
			smsc = "+"+smsc
		if num[0] != "0" and num[0] != "+":
			num = "+"+num
		### Log('createSMS new msg (1): NUM: '+num+", MSG: "+msg+", SMSC: "+smsc+", LEN:"+str(len(msg))+", HASH: "+shahash)
		
		#reaplace unusual characters and white spaces
		msg=msg.replace("*","")
		msg=msg.replace("\t"," ")
		msg=msg.replace("\n"," ")
		while True:
			if "  " in msg:
				msg=msg.replace("  "," ")
			else:
				break
		msg=strip(msg)
		if len(msg) > SMSLENGTH:
			Log('createSMS cutted msg: '+msg)
			msg=msg[0:SMSLENGTH]
		Log('createSMS new msg: NUM: '+num+", MSG:"+msg+", SMSC: "+smsc+", MSGLEN:"+str(len(msg))+", ID: "+shahash)
		
		#create sms format pdu
		y=strftime("%Y", gmtime())
		sms = SmsSubmit(num, msg)
		
		#validity= end of this year
		sms.validity = datetime(int(y)+1, 12, 31, 23, 59, 59)
		sms.csca = smsc
		pdu = sms.to_pdu()[0]
		
		s=pdu.pdu
		#print s
		
		##calculate checksum
		l=0
		sum=0
		for i in xrange(len(s)):
			if (i == 0 or i%2 == 0):
				j=i+2
				h= s[i:j]
				#print "hex:",h
				ih=int(h,16)
				#print "int:",str(ih)
				sum=(sum+ih) % 256
			l+=1
		fulllength=str((l/2)-8)
		chsum=str(hex(sum))[2:]
		#print "length: ",fulllength
		#print "sum: ",chsum

		tosend="AT^SM=32,"+fulllength+","+s+","+chsum
		#print "pdu:", tosend
		
		#try to send sms 5 times:
		Log('createSMS: SMS SENDING, BODY: '+str(tosend))
		msgsent=self.CommandSender(tosend,False,False,"smsout",20)
		
		#if not sent, put back to the queue:
		if not msgsent:
			Log('createSMS ERROR: cannot send SMS. Put back to INQ:'+str(msgsent))
			nowdate=str(strftime('%Y-%m-%d %H:%M:%S', localtime()))
			sqlobj=initSQLite(True)
			qry="UPDATE sms SET status = 'senderror', lastdate='"+nowdate+"'  WHERE hash = '"+shahash+"'"
			SQLiteExec(qry,sqlobj)
			SQLiteClose(sqlobj)
			###INQ.put_nowait([num,msg,smsc,shahash])
			sleep(1)
			return False
		
		#if sent: change status:
		else:
			nowdate=str(strftime('%Y-%m-%d %H:%M:%S', localtime()))
			sqlobj=initSQLite(True)
			qry="UPDATE sms SET status = 'sent', lastdate='"+nowdate+"'  WHERE hash = '"+shahash+"'"
			SQLiteExec(qry,sqlobj)
			SQLiteClose(sqlobj)
			Log('createSMS: SMS sent OK:'+str(msgsent))
			return True
			
	def deleteSMSFromSIM(self,cardnum="0",smsnum="1"):
		tosend = "AT^SD="+cardnum+","+smsnum
		delsms=self.CommandSender(tosend,False,True,"smsdel",10)
		Log("deleteSMSFromSIM: "+str(delsms))
		return None
		
	def processSMS(self,pdu=None,cardnum="0"):
		if not pdu or not len(strip(pdu)):
			return False
		sms=None
		try:
			sms=SmsDeliver(pdu)
		except:
			pass
		if sms:
			sender = sms.data['number']
			msg = sms.data['text']
			msg = msg.encode('utf-8')
			smsdate = sms.data['date'].strftime('%Y-%m-%d %H:%M:%S')
			h=hashlib.sha1()
			h.update(str(smsdate)+str(sender)+str(msg))
			shahash=h.hexdigest()
			sqlobj=initSQLite(True)
			qry_check = "SELECT 1 FROM sms WHERE hash = '"+shahash+"'"
			check=SQLiteQuery(qry_check,sqlobj,True)
			if not check:
				qry = "INSERT INTO sms (	smsdate, \
											cardnum, \
											fromnum, \
											status, \
											deleted, \
											hash, \
											msg ) VALUES ( \
											'"+str(smsdate)+"', \
											'"+str(cardnum)+"', \
											'"+str(sender)+"', \
											'received', \
											'no', \
											'"+str(shahash)+"', \
											'"+str(msg)+"') \
				"
				rowid=SQLiteExec(qry,sqlobj)
				SQLiteClose(sqlobj)
				if rowid > 0:
					return True
				else:
					return False
			elif check < 0:
				SQLiteClose(sqlobj)
				return False
			else:
				SQLiteClose(sqlobj)
				return True

	def fetchSMS(self,cardnum="0",smsnum="1"):
		tosend = "AT^SR="+cardnum+","+smsnum
		smspdu=self.CommandSender(tosend,False,True,"smspdu",10)
		#print "-----------"
		#print smspdu
		if smspdu and len(smspdu):
			smspduary=smspdu.split(NL)
		else:
			Log("fetchSMS ERROR: "+str(smspdu))
			return False
		for rawsms in smspduary:
			if "*smspdu: " not in rawsms:
				if len(strip(rawsms)):
					###Log("fetchSMS debug1: "+str(rawsms))
					pass
				continue
			rawsmsary=rawsms.split("*smspdu: ")
			if "," not in rawsmsary[1]:
				if len(strip(rawsmsary[1])):
					Log("fetchSMS debug2: "+str(rawsmsary))
				continue
			smsary=rawsmsary[1].split(",")
			pdu=smsary[-2]
			result=self.processSMS(pdu,cardnum)
			if result:
				self.deleteSMSFromSIM(cardnum,smsnum)
			

	def checkNewSMSes(self):
		for cnum in SIMCARDSINUSE:
			cnum=str(cnum)
			tosend = "AT^SX="+cnum
			smses=self.CommandSender(tosend,False,True,(cnum+",0,0,255"),20)
			if smses and len(smses):
				smsary=smses.split(NL)
			else:
				Log("checkNewSMSes ERROR: "+str(smses))
				return False
			for sms in smsary:
				if tosend not in sms:
					if "*smsinc: " not in sms:
						if len(strip(sms)):
							Log("checkNewSMSes debug1: "+str(sms))
						continue
					smsnums=sms.split("*smsinc: ")
					if "," not in smsnums[1]:
						if len(strip(smsnums[1])):
							Log("checkNewSMSes debug2: "+str(smsnums))
						continue
					msgary=smsnums[1].split(",")
					cardnum=str(msgary[0])
					smsnum=str(msgary[1])
					end=str(msgary[-1])
					if end == "255":
						continue
					self.fetchSMS(cardnum,smsnum)

	def SerialControllerThread(self):
		global NEND
		z=0
		while NEND:
			#try:
			item=None
			if not INQ.empty():
				item = INQ.get_nowait()
				print "INQ item:"
				print item
			if not item:
				if z >= SIMPOLLINTERVAL:
					self.checkNewSMSes()
					z=0
				z+=1
				sleep(1)
				continue
			if item and item == "***":
				break
			if item and len(item) == 4:
				self.createSMS(item[0],item[1],item[2],item[3])
			if INQ.empty():
				try:
					INQ.task_done()
				except:
					pass
			sleep(1)
			#except Exception,e:
			#	Log('SMSQThread Exception:',e)
			#	sleep(1)
			#	continue
		NEND=False
		sys.exit(1)

class SMSRequestHandler(BaseHTTPRequestHandler):
	
	def do_HEAD(self):
		self.send_response(200)
		self.send_header("Content-type", "text/xml; charset=UTF-8")
		self.end_headers()
	
	def do_GET(self):
		self.send_response(200)
		self.send_header("Content-type", "text/xml; charset=UTF-8")
		self.end_headers()
		self.wfile.write('<?xml version="1.0" encoding="UTF-8"?>')
		qspos = self.path.find('?')
		if qspos>=0:
			self.body = cgi.parse_qs(self.path[qspos+1:], keep_blank_values=1)
			self.path = self.path[:qspos]
		else:
			self.body = ''
			self.path = '/'
		self.processrequest()
		
	def do_POST(self):
		self.send_response(200)
		self.send_header("Content-type", "text/xml; charset=UTF-8")
		self.end_headers()
		self.wfile.write('<?xml version="1.0" encoding="UTF-8"?>')
		ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
		length = int(self.headers.getheader('content-length'))
		if ctype == 'multipart/form-data':
			self.body = cgi.parse_multipart(self.rfile, pdict)
		elif ctype == 'application/x-www-form-urlencoded':
			self.body = cgi.parse_qs(self.rfile.read(length), keep_blank_values=1)
		else:
			self.body = ''
		self.processrequest()
	
	def remove_accents(self,i):
		return unicodedata.normalize('NFKD', unicode(i,'utf-8')).encode('ASCII', 'ignore')
	
	def getRequest(self,bodyvarname):
		d=''
		if not type(self.body).__name__ == 'dict':
			return d
		try:
			if (self.body.has_key(bodyvarname) or self.body.has_key(bodyvarname.upper())):
				if (self.body.has_key(bodyvarname)):
					d=strip(str(self.body[bodyvarname][0]))
				elif (self.body.has_key(bodyvarname.upper())):
					d=strip(str(self.body[bodyvarname.upper()][0]))
				d=str(d)
				return d
			else:
				return d
		except Exception,e:
			Log('SMSRequestHandler: getRequest : Exception, self.body:'+str(self.body))
			return d
			
	def receiveSMS(self,rcpt,msg='',smsc=''):
		if not len(smsc):
			smsc=SMSC
		if not smsc or not rcpt:
			Log('SMSRequestHandler: processrequest ERROR: INCOMPLETE DATA! RCPT:'+rcpt+", MSG: "+msg+", SMSC: "+smsc)
			return None
		if not msg or not len(msg.strip()):
			msg=''
		h=hashlib.sha1()
		h.update(str(time())+str(rcpt)+str(msg))
		shahash=h.hexdigest()
		#num,msg,smsc,sha
		#put into sql db
		nowdate=str(strftime('%Y-%m-%d %H:%M:%S', localtime()))
		sqlobj=initSQLite(True)
		qry = "INSERT INTO sms (	smsdate, \
									tonum, \
									hash, \
									status, \
									deleted, \
									msg ) VALUES ( \
									'"+nowdate+"', \
									'"+str(rcpt)+"', \
									'"+str(shahash)+"', \
									'queued', \
									'no', \
									'"+str(msg)+"') \
		"
		rowid=SQLiteExec(qry,sqlobj)
		SQLiteClose(sqlobj)
		INQ.put_nowait([rcpt,msg,smsc,shahash])
		Log('SMSRequestHaput_nowaitndler: processrequest : New message: RCPT:'+rcpt+", MSG: "+msg+", SMSC: "+smsc+", SQLROWID: "+str(rowid))
		if rowid > 0:
			self.wfile.write('<response type="send">'+NL+"<status>OK</status>"+NL+"<date>"+nowdate+"</date>"+NL+"<id>"+shahash+"</id>"+NL+"</response>"+NL)
		else:
			self.wfile.write('<response type="send">'+NL+"<status>ERROR</status>"+NL+"<date>"+nowdate+"</date>"+NL+"<id>"+shahash+"</id>"+NL+"</response>"+NL)
		return
		
	def listAllSMS(self,showdeleted=0):
		sqlobj=initSQLite(True)
		f=''
		if showdeleted == 1:
			f=" WHERE deleted = 'no' "
		elif showdeleted == 2:
			f=" WHERE deleted = 'yes' "
		elif showdeleted == 3:
			f=" WHERE deleted = 'no' AND status = 'received' "
		elif showdeleted == 4:
			f=" WHERE deleted = 'yes' AND status = 'received' "
		elif showdeleted == 5:
			f=" WHERE deleted = 'no' AND status = 'sent' "
		elif showdeleted == 6:
			f=" WHERE deleted = 'yes' AND status = 'sent' "
		elif showdeleted == 7:
			f=" WHERE status = 'queued' "
		elif showdeleted == 8:
			f=" WHERE status = 'senderror' "
		qry = "SELECT \
				smsdate, \
				lastdate, \
				cardnum, \
				fromnum, \
				tonum, \
				status, \
				deleted, \
				hash, \
				msg \
			FROM sms "+f+" ORDER BY smsdate DESC"
		res = SQLiteQuery(qry,sqlobj)
		SQLiteClose(sqlobj)
		self.wfile.write('<response type="receive">'+NL)
		for sms in res:
			self.wfile.write("<sms>"+NL)
			smsdate,lastdate,cardnum,fromnum,tonum,status,deleted,hash,msg = sms
			cardnum=str(cardnum)
			msg=msg.encode("utf-8")
			self.wfile.write("<id>"+str(hash)+"</id>"+NL)
			self.wfile.write("<smsdate>"+str(smsdate)+"</smsdate>"+NL)
			self.wfile.write("<lastdate>"+str(lastdate)+"</lastdate>"+NL)
			self.wfile.write("<cardnum>"+str(cardnum)+"</cardnum>"+NL)
			self.wfile.write("<fromnum>"+str(fromnum)+"</fromnum>"+NL)
			self.wfile.write("<tonum>"+str(tonum)+"</tonum>"+NL)
			self.wfile.write("<status>"+str(status)+"</status>"+NL)
			self.wfile.write("<deleted>"+str(deleted)+"</deleted>"+NL)
			self.wfile.write("<msg><![CDATA["+msg+"]]></msg>"+NL)
			self.wfile.write("</sms>"+NL)
		self.wfile.write('</response>'+NL)
		return
		
	def delSMS(self,msgid):
		nowdate=str(strftime('%Y-%m-%d %H:%M:%S', localtime()))
		sqlobj=initSQLite(True)
		qry="UPDATE sms SET deleted='yes', lastdate='"+nowdate+"'  WHERE hash = '"+msgid+"'"
		rowid=SQLiteExec(qry,sqlobj)
		SQLiteClose(sqlobj)
		Log('delSMS: delete request for sms: '+str(msgid)+', status: '+str(rowid))
		if rowid > 0:
			self.wfile.write('<response type="delete">'+NL+"<status>OK</status>"+NL+"<date>"+nowdate+"</date>"+NL+"<id>"+msgid+"</id>"+NL+"</response>"+NL)
		else:
			self.wfile.write('<response type="delete">'+NL+"<status>ERROR</status>"+NL+"<date>"+nowdate+"</date>"+NL+"<id>"+msgid+"</id>"+NL+"</response>"+NL)
		return
		
	def truncateSMS(self):
		nowdate=str(strftime('%Y-%m-%d %H:%M:%S', localtime()))
		sqlobj=initSQLite(True)
		qry="DELETE FROM sms WHERE deleted='yes'"
		rowid=SQLiteExec(qry,sqlobj)
		SQLiteClose(sqlobj)
		Log('truncateSMS: remove deleted SMSes, status: '+str(rowid))
		if rowid > 0:
			self.wfile.write('<response type="truncate">'+NL+"<status>OK</status>"+NL+"<date>"+nowdate+"</date>"+NL+"<pcs>"+str(rowid)+"</pcs>"+NL+"</response>"+NL)
		else:
			self.wfile.write('<response type="truncate">'+NL+"<status>ERROR</status>"+NL+"<date>"+nowdate+"</date>"+NL+"<pcs>"+str(rowid)+"</pcs>"+NL+"</response>"+NL)
		return

	def processrequest(self):
		
		#handle request variables
		smsc=self.getRequest("smsc")
		rcpt=self.getRequest("rcpt")
		msg=self.remove_accents(self.getRequest("msg"))
		action=self.getRequest("action")
		msgid=self.getRequest("id")
		
		#sqlinjection basic prevent
		smsc=smsc.replace('"','').replace("'","")
		rcpt=rcpt.replace('"','').replace("'","")
		msg=msg.replace('"','').replace("'","")
		action=action.replace('"','').replace("'","")
		msgid=msgid.replace('"','').replace("'","")
		
		rcpt=phoneNumFormatter(rcpt)
		
		#send sms
		if rcpt:
			self.receiveSMS(rcpt,msg,smsc)
			return
		#list all sms
		elif action == "listall":
			self.listAllSMS()
		
		#list only not deleted
		elif action == "list":
			self.listAllSMS(1)
		
		#list only deleted
		elif action == "listdel":
			self.listAllSMS(2)
			
		#list received
		elif action == "listrec":
			self.listAllSMS(3)
			
		#list received deleted
		elif action == "listrecdel":
			self.listAllSMS(4)
			
		#list sent
		elif action == "listsent":
			self.listAllSMS(5)
			
		#list sent deleted
		elif action == "listsentdel":
			self.listAllSMS(6)
			
		#list queued
		elif action == "listqueue":
			self.listAllSMS(7)
			
		#list errors
		elif action == "listerr":
			self.listAllSMS(8)
			
		#delete sms
		elif action == "delete" and len(msgid) == 40:
			self.delSMS(msgid)
			
		#truncate deleted smses
		elif action == "truncate":
			self.truncateSMS()
		
		#error
		else:
			self.wfile.write('<response type="error">'+NL)
			self.wfile.write('<error>insufficient request</error>'+NL)
			self.wfile.write('</response>'+NL)
		return


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
	pass

def __serve_on_port(port):
	try:
		server = ThreadingHTTPServer(("0.0.0.0",int(port)), SMSRequestHandler)
		server.serve_forever()
	except Exception,e:
		Log("__serve_on_port Exception",e)
		INQ.put_nowait("***")
		NEND=False
		Log('Main: Application exit.')
		sleep(1)
		pid=os.getpid()
		os.kill(pid, signal.SIGKILL)


############################
# start main program
############################
if __name__=="__main__":
	Log("Main: START Application "+sys.argv[0]+" ...")
	Log('---------------------')
	
	#check sqlitepath
	sqlpath=os.path.dirname(SQLITE_PATH)
	if not os.path.exists(sqlpath):
		try:
			os.makedirs(sqlpath)
		except Exception,e:
			Log("Cannot create SQLITE_PATH, sysexit: "+sqlpath,e)
			NEND=False
			sys.exit(1)
	
	#init sql database
	sqlite = initSQLite()
	if not sqlite:
		Log("Cannot init SQLite database, sysexit!")
		NEND=False
		sys.exit(1)
	
	serhandler=USBSerialHandler()
	Thread(target=__serve_on_port, args=[PORT]).start()
	Log("Server listens on HTTP PORT: "+str(PORT))
	
	#start keyboard and INT (interrupt signal) watcher
	try:
		while NEND:
			sleep(1)
			continue
		NEND=False
	except (KeyboardInterrupt, SystemExit):
		Log('Main: Application: '+sys.argv[0]+': interrupted. KeyboardInterrupt or SIG.INT received.',"",True)
		sleep(0.5)
		INQ.put_nowait("***")
		NEND=False
		Log('Main: Application exit.')
		sleep(0.5)
		pid=os.getpid()
		os.kill(pid, signal.SIGKILL)
	sys.exit(1)

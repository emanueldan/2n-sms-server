#!/bin/bash

### BEGIN INIT INFO
# Provides:			2nVoiceBlueSMSServer start-strop script
# Required-Start:	$all
# Required-Stop:	$all
# Default-Start:	2 3 4 5
# Default-Stop:		0 1 6
# Short-Description: This start-stop script used in Debian based systems.
# Description:		VoiceBlue VoIP modems SMS server via USB serial port.
### END INIT INFO

PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
DAEMON=/usr/local/bin/2nVoiceBlueSMSServer.py
NAME=VoiceBlueSMSServer
DESC=VoiceBlueSMSServer
SSDMON=`which start-stop-daemon`

#set variables 
RUN_USER=root
RUN_GROUP=root
RUN_UMASK=022
MAX_ALIVE=
RUN_NICENESS=

#set wrapper options 
WRAPPER_OPTIONS=""
WRAPPER_OPTIONS="$WRAPPER_OPTIONS --chuid $RUN_USER:$RUN_GROUP"
WRAPPER_OPTIONS="$WRAPPER_OPTIONS --group $RUN_GROUP"
WRAPPER_OPTIONS="$WRAPPER_OPTIONS --umask $RUN_UMASK"
WRAPPER_OPTIONS="$WRAPPER_OPTIONS --user $RUN_USER"

test -f $DAEMON || exit 0
chmod +x $DAEMON
test -x $DAEMON || exit 0

PID=`/bin/ps ax | grep "$NAME" | grep "py" | grep -v "grep" | /usr/bin/awk '{print $1}'`

case "$1" in
  start)
	echo -n "Starting $DESC: "
	if [ ! -n "$PID" ]; 
	then
		if [ -n "$SSDMON" ]; 
		then
			start-stop-daemon --start $WRAPPER_OPTIONS --background --exec $DAEMON -- $CONF
		else
			nohup python $DAEMON > /dev/null 2>&1 &
		fi
	else
		echo "Program already running: $PID , please stop it first."
	fi
		echo "$NAME."
		;;
  fg)
	echo -n "Starting $DESC in foreground: "
	if [ ! -n "$PID" ]; 
	then
		if [ -n "$SSDMON" ];
		then
			start-stop-daemon --start $WRAPPER_OPTIONS --exec $DAEMON -- $CONF
		else
			python $DAEMON
		fi
	else
		echo "Program already running: $PID , please stop it first."
	fi
		echo "$NAME."
		;;
  stop)
		echo -n "Stopping $DESC: "
		echo -n $PID
		/bin/kill -s INT $PID > /dev/null 2>&1
		sleep 5
		/bin/kill -9 $PID > /dev/null 2>&1 &
		sleep 1
		echo "."
		;;
  status)
		echo -n "Status PID $DESC: "
		echo -n $PID
		echo "."
		;;
  restart|force-reload)
		echo -n "Restarting $DESC: "
		echo -n $PID
		/bin/kill -s INT $PID > /dev/null 2>&1
		sleep 5
		/bin/kill -9 $PID > /dev/null 2>&1 &
		sleep 3
		if [ -n "$SSDMON" ]; 
		then
			start-stop-daemon --start $WRAPPER_OPTIONS --background --exec $DAEMON -- $CONF
		else
			nohup python $DAEMON > /dev/null 2>&1 &
		fi
		echo "."
		;;
  *)
		N=/etc/init.d/$NAME
		echo "Usage: $N {start|fg|stop|restart}" >&2
		exit 1
		;;
esac
exit 0


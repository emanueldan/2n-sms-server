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
PIDFILE=/var/run/$NAME.pid

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

if [ -f $PIDFILE ];
then
		pid1=`cat $PIDFILE`
fi;

PID=`/bin/ps ax | grep "$NAME" | grep "py" | grep -v "grep" | /usr/bin/awk '{print $1}'`

case "$1" in
  start)
	echo -n "Starting $DESC: "
	if [ -f $PIDFILE ]; 
	then
		# echo pid file found...
		if [ "$pid1" == "$PID"  ]; 
		then
			echo "Program already running: $PID"
			exit 0
		else
			start-stop-daemon --start $WRAPPER_OPTIONS --make-pidfile --pidfile $PIDFILE --background --exec $DAEMON -- $CONF
		fi
	else
		start-stop-daemon --start $WRAPPER_OPTIONS --make-pidfile --pidfile $PIDFILE --background --exec $DAEMON -- $CONF
	fi
		echo "$NAME."
		;;
  fg)
	echo -n "Starting $DESC in foreground: "
	if [ -f $PIDFILE ]; 
	then
		# echo pid file found...
		if [ "$pid1" == "$PID"  ]; 
		then
			echo "Program already running: $PID"
			exit 0
		else
			start-stop-daemon --start $WRAPPER_OPTIONS --make-pidfile --pidfile $PIDFILE --exec $DAEMON -- $CONF
		fi
	else
		start-stop-daemon --start $WRAPPER_OPTIONS --make-pidfile --pidfile $PIDFILE --exec $DAEMON -- $CONF
	fi
		echo "$NAME."
		;;
  stop)
		echo -n "Stopping $DESC: "
		echo -n $PID
		/bin/kill -s INT $PID > /dev/null 2>&1
		sleep 3
		/bin/kill -9 $PID > /dev/null 2>&1 &
		echo "."
		;;
  status)
		echo -n "Status $DESC: "
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
		start-stop-daemon --start $WRAPPER_OPTIONS --make-pidfile --pidfile $PIDFILE --background --exec $DAEMON -- $CONF
		echo "."
		;;
  *)
		N=/etc/init.d/$NAME
		echo "Usage: $N {start|fg|stop|restart|force-reload}" >&2
		exit 1
		;;
esac
exit 0


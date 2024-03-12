#!/bin/sh

# This makes a CSV user-list to add users in a group.  It takes a
# group as an argument.  It generates entries like:
# "ADD,username,,group1,group2,..."  It drops the system groups listed
# in /etc/group.  Add group names in $sysgrp to increase the drop list
# by: sysgrp+=("wheel" "admins").

m=$1

# $uu lists the members of a group.

uu=`getent group $m | sed -e 's/^[^:]*:\*\:[0-9]*://' -e 's/,/\n/g'`

# $sysgrp is a group list to be dropped.

sysgrp=($(cat /etc/group | sed -e 's/^\([^:]*\).*$/\1/'))
sysgrp+=("wheel" "admins")

make_entry () {
u=$1
e="ADD,$u,"
for g in `id -nG $u`
do
    if ! echo " ${sysgrp[@]} " | grep -F " $g " > /dev/null 2>&1 ; then
        e="$e,$g"
    fi
done
echo $e
}

for u in $uu
do
    make_entry $u
done

This directory contains scripts to build lxc environment
(Ubuntu 20.04 is assumed as host OS)

1. Install lxd

  ```
  # apt install -y lxd
  $ lxd init
  ```


2. Create lxc container

  ```
  $ make create
  $ make start
  $ make install
  ```

3. ssh to created environment

  ```
  $ ssh Re
  ```


A.
  All scripts in this directory are assumed to be 
  called from `makefile`.
  To understand what is done by these scripts, please 
  start reading from `makefile`.

#
# Copyright (c) 2013 Oracle and/or its affiliates. All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA
#

""" This module contains functions that are called from the services interface
and change MySQL state. Notice though that after a failure the system does no
undo the changes made through the execution of these functions.
"""
import mysql.fabric.replication as _replication

def switch_master(slave, master):
    """Make slave point to master.

    :param slave: Slave.
    :param master: Master.
    """
    _replication.stop_slave(slave, wait=True)
    _replication.switch_master(slave, master, master.user, master.passwd)
    slave.read_only = True
    _replication.start_slave(slave, wait=True)


def set_read_only(server, read_only):
    """Set server to read only mode.

    :param read_only: Either read-only or not.
    """
    server.read_only = read_only


def reset_slave(slave):
    """Stop slave and reset it.

    :param slave: slave.
    """
    _replication.stop_slave(slave, wait=True)
    _replication.reset_slave(slave, clean=True)


def process_slave_backlog(slave, gtid_executed, gtid_retrieved):
    """Wait until slave processes its backlog.

    :param slave: slave.
    :param gtid_executed: Executed GTIDs.
    :param gtid_retrieved: Retrieved GTIDs.
    """
    _replication.stop_slave(slave, wait=True)
    _replication.start_slave(slave, threads=("SQL_THREAD", ), wait=True)
    _replication.wait_for_slave_gtid(slave, gtid_executed + "," + \
                                     gtid_retrieved)


def synchronize(slave, master):
    """Synchronize a slave with a master and after that stop the slave.

    :param slave: Slave.
    :param master: Master.
    """
    _replication.sync_slave_with_master(slave, master, timeout=0)


def stop_slave(slave):
    """Stop slave.

    :param slave: Slave.
    """
    _replication.stop_slave(slave, wait=True)

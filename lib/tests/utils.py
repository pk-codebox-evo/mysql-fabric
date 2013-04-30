"""Module holding support utilities for tests.
"""
import glob
import os
import threading
import time
import uuid as _uuid
import xmlrpclib
import logging

from mysql.hub import (
    config as _config,
    persistence as _persistence,
    replication as _replication,
    server as _server,
    utils as _utils,
    )

from mysql.hub.sharding import ShardMapping, RangeShardingSpecification

_LOGGER = logging.getLogger(__name__)

class MySQLInstances(_utils.Singleton):
    """Contain a reference to the available set of MySQL Instances that can be
    used in a test case.
    """
    def __init__(self):
        """Constructor for MySQLInstances.
       """
        super(MySQLInstances, self).__init__()
        self.__addresses = []
        self.__instances = {}

    def add_address(self, address):
        """Add the address of a MySQL Instance that can be used in the test
        cases.

        :param address: MySQL's address.
        """
        assert(isinstance(address, basestring))
        self.__addresses.append(address)

    def get_number_addresses(self):
        """Return the number of MySQL Instances' address registered.
        """
        return len(self.__addresses)

    def get_address(self, number):
        """Return the n-th address registerd.
        """
        assert(number < len(self.__addresses))
        return self.__addresses[number]

    def get_instance(self, number):
        """Return the n-th instance created through the
        :meth:`configure_instances` method.

        :return: Return a MySQLServer object.
        """
        assert(number < len(self.__addresses))
        return self.__instances[number]

    def destroy_instances(self):
        """Destroy the MySQLServer objects created through the
        :meth:`configure_instances` method.
        """
        for instance in self.__instances.values():
            _replication.stop_slave(instance, wait=True)
            _replication.reset_slave(instance, clean=True)
        self.__instances = {}

    def configure_instances(self, topology, user, passwd):
        """Configure a replication topology using the MySQL Instances
        previously registerd.

        :param topology: Topology to be configured.
        :param user: MySQL Instances' user.
        :param passwd: MySQL Instances' password.

        This method can be used as follows::

          import tests.utils as _test_utils

          topology = {1 : [{2 : []}, {3 : []}]}
          instances = _test_utils.MySQLInstances()
          instances.configure_instances(topology, "root", "")

        Each instance in the topology is represented as a dictionary whose
        keys are references to addresses that will be retrieved through
        the :meth:`get_address` method and values are a list of slaves.

        So after calling :meth:`configure_instances` method, one can get a
        reference to an object, MySQLServer, through the :meth:`get_instance`
        method.
        """
        for number in topology.keys():
            master_address = self.get_address(number)

            master_uuid = _server.MySQLServer.discover_uuid(
                address=master_address, user=user, passwd=passwd)
            master = _server.MySQLServer(
                _uuid.UUID(master_uuid), master_address, user, passwd)
            master.connect()
            _replication.stop_slave(master, wait=True)
            _replication.reset_master(master)
            _replication.reset_slave(master)
            master.read_only = False
            self.__instances[number] = master
            for slave_topology in topology[number]:
                slave = self.configure_instances(slave_topology, user, passwd)
                slave.read_only = True
                _replication.switch_master(slave, master, user, passwd)
                _replication.start_slave(slave, wait=True)
            return master

class ShardingUtils(object):
    @staticmethod
    def compare_shard_mapping(shard_mapping_1, shard_mapping_2):
        """Compare two sharding mappings with each other. Two sharding
        specifications are equal if they have the same id, are defined
        on the same table, on the same column, are of the same type and
        use the same global group.

        :param shard_mapping_1: shard mapping
        :param shard_mapping_2: shard mapping

        :return True if shard mappings are equal
                False if shard mappings are not equal
        """
        return isinstance(shard_mapping_1, ShardMapping) and \
                isinstance(shard_mapping_2, ShardMapping) and \
               shard_mapping_1.shard_mapping_id == \
                        shard_mapping_2.shard_mapping_id and \
               shard_mapping_1.table_name == \
                        shard_mapping_2.table_name and \
                shard_mapping_1.column_name == \
                        shard_mapping_2.column_name and \
                shard_mapping_1.type_name == \
                            shard_mapping_2.type_name and \
                shard_mapping_1.global_group == \
                            shard_mapping_2.global_group
    @staticmethod
    def compare_range_specifications(range_specification_1,
                                     range_specification_2):
        """Compare two RANGE specification definitions. They are equal if they
        belong to the same shard mapping, define the same upper and lower
        bound, map to the same shard, and are in the same state.

        :param range_specification_1: Range Sharding Specification
        :param range_specification_2: Range Sharding Specification

        :return: If Range Sharding Specifications are equal, it returns True.
                 False if Range Sharding Specifications are not equal
        """
        return \
            isinstance(range_specification_1, RangeShardingSpecification) and \
            isinstance(range_specification_2, RangeShardingSpecification) and \
                range_specification_1.shard_mapping_id == \
                        range_specification_2.shard_mapping_id and \
                range_specification_1.lower_bound == \
                        range_specification_2.lower_bound and \
                range_specification_1.upper_bound == \
                        range_specification_2.upper_bound and \
                range_specification_1.shard_id == range_specification_2.shard_id and \
                range_specification_1.state == range_specification_2.state

def cleanup_environment():
   #Stop slaves and reset slaves on all servers
    MySQLInstances().destroy_instances()
   #Remove all the databases from the running MySQL instances
   #other than the standard ones
    STANDARD_DB_LIST = ("information_schema", "mtr", "mysql", "performance_schema", "test")
    server_count = MySQLInstances().get_number_addresses()
    for i in range(0, server_count):
        __options = {
            "uuid" :  _uuid.UUID("{cc75b12b-98d1-414c-96af-9e9d4b179678}"),
            "address"  : MySQLInstances().get_address(i),
            "user" : "root"
        }

        __uuid_server = _server.MySQLServer.discover_uuid(**__options )
        __options ["uuid"] = _uuid.UUID(__uuid_server)
        __server = _server.MySQLServer(**__options )
        __server.connect()
        _replication.reset_master(__server)
        databases = __server.exec_stmt(
                                "SHOW DATABASES",
                                {"fetch" : True})
        databases_count = len(databases)
        for j in range(0, databases_count):
            if databases[j][0] not in STANDARD_DB_LIST:
                __server.exec_stmt("DROP DATABASE IF EXISTS %s" % (databases[j][0]))

    files = glob.glob(os.path.join(os.getcwd(), "*.sql"))
    for f in files:
        os.remove(f)
    
def setup_xmlrpc():
    # TODO: Check the xmlrpc_next_port...
    from __main__ import options, xmlrpc_next_port, mysqldump_path, mysqlclient_path
    params = {
        'protocol.xmlrpc': {
            'address': 'localhost:%d' % (xmlrpc_next_port, ),
            },
        'storage': {
            'address': options.host + ":" + str(options.port),
            'user': options.user,
            'password': options.password,
            'database': 'fabric',
            'connection_timeout': 'None',
            },
            'sharding': {
                'mysqldump_program': mysqldump_path,
                'mysqlclient_program': mysqlclient_path,
            }, 
        }
    config = _config.Config(None, params, True)

    # Set up the manager
    from mysql.hub.services.manage import (
        _start,
        _configure_connections,
        )

    _configure_connections(config)
    _persistence.setup()
    manager_thread = threading.Thread(
        target=_start, name="Services", args=(options, config)
        )
    manager_thread.daemon = True
    manager_thread.start()

    # Set up the client
    url = "http://%s" % (config.get("protocol.xmlrpc", "address"),)
    proxy = xmlrpclib.ServerProxy(url)

    while True:
        try:
            proxy.manage.ping()
            break
        except Exception:
            time.sleep(1)

    return (manager_thread, proxy)

def teardown_xmlrpc(manager, proxy):
    proxy.manage.stop()
    manager.join()
    _persistence.teardown()

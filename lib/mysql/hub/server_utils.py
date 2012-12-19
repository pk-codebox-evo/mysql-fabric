"""Define functions that can be used throughout the code.
"""
import logging
import collections
try:
    import mysql.connector
    from mysql.connector.cursor import MySQLCursor, MySQLCursorRaw
except ImportError:
    pass

import mysql.hub.errors as _errors

_LOGGER = logging.getLogger(__name__)

MYSQL_DEFAULT_PORT = 3306

def split_host_port(uri, default_port):
    """Return a tuple with host and port.

    If a port is not found in the uri, the default port is returned.
    """
    if uri.find(":") >= 0:
        host, port = uri.split(":")
    else:
        host, port = (uri, default_port)
    return host, port

def combine_host_port(host, port, default_port):
    """Return a string with the parameters host and port.

    :return: String host:port.
    """
    if host:
        if host == "127.0.0.1":
            host_info = "localhost"
        else:
            host_info = host
    else:
        host_info = "unknown host"

    if port:
        port_info = port
    else:
        port_info = default_port

    return "%s:%s" % (host_info, port_info)

try:
    def _null_converter(description, value):
        """Return the value passed as parameter without any conversion.
        """
        return value

    def _do_row_to_python(self, convert, rowdata, desc=None):
        """Created a named tuple with retrived data from a database.
        """
        try:
            if not desc:
                desc = self.description
            row = (convert(desc[i], v) for i, v in enumerate(rowdata))
            tuple_factory = \
                collections.namedtuple('Row', self.column_names)._make
            return tuple_factory(row)
        except StandardError as error:
            raise mysql.connector.errors.InterfaceError(
                "Failed converting row to Python types; %s" % error)

    class MySQLCursorNamedTuple(MySQLCursor):
        """Create a cursor with named columns and non-raw data.
        """
        def _row_to_python(self, rowdata, desc=None):
            return _do_row_to_python(self,
                                     self._connection.converter.to_python,
                                     rowdata, desc)

    class MySQLCursorRawNamedTuple(MySQLCursor):
        """Create a cursor with named columns and raw data.
        """
        def _row_to_python(self, rowdata, desc=None):
            return _do_row_to_python(self, _null_converter, rowdata, desc)
except NameError:
    pass

# TODO: Extend this to accept list of statements.
def exec_mysql_stmt(cnx, stmt_str, options=None):
    """Execute a statement for the client and return a result set or a
    cursor.

    This is the singular method to execute queries. If something goes
    wrong while executing a statement, the exception
   :class:`mysql.hub.errors.DatabaseError` is raised.

    :param cnx: Database connection.
    :param stmt_str: The statement (e.g. query, updates, etc) to execute.
    :param options: Options to control behavior:

                    - params - Parameters for statement.
                    - columns - If true, return a rows as named tuples
                      (default is False).
                    - raw - If true, do not convert MySQL's types to
                      Python's types (default is True).
                    - fetch - If true, execute the fetch as part of the
                      operation (default is True).

    :return: Either a result set as list of tuples (either named or unnamed)
             or a cursor.
    """
    if cnx is None or not cnx.is_connected():
        raise _errors.DatabaseError("Connection is invalid.")

    options = options or {}
    params = options.get('params', ())
    columns = options.get('columns', False)
    fetch = options.get('fetch', True)
    raw = options.get('raw', True)

    if raw and columns:
        cursor_class = MySQLCursorRawNamedTuple
    elif not raw and columns:
        cursor_class = MySQLCursorNamedTuple
    elif raw and not columns:
        cursor_class = MySQLCursorRaw
    elif not raw and not columns:
        cursor_class = MySQLCursor

    _LOGGER.debug("Statement (%s), Params(%s).", stmt_str, params)

    cur = cnx.cursor(cursor_class=cursor_class)

    try:
        cur.execute(stmt_str, params)
    except mysql.connector.Error as error:
        cur.close()
        raise _errors.DatabaseError(
            "Command (%s, %s) failed: %s" % (stmt_str, params, str(error)),
            error.errno)
    except Exception as error:
        cur.close()
        raise _errors.DatabaseError(
            "Unknown error. Command: (%s, %s) failed: %s" % (stmt_str, \
            params, str(error)))

    if fetch:
        results = None
        try:
            results = cur.fetchall()
        except mysql.connector.errors.InterfaceError as error:
            # TODO: This is a temporary solution. In the future, the
            # python connector should provide a function to return
            # cur._have_result.
            if error.msg.lower() == "no result set to fetch from.":
                pass # This error means there were no results.
            else:    # otherwise, re-raise error
                raise _errors.DatabaseError(
                    "Error (%s) fetching data for statement: (%s)." % \
                    (str(error), stmt_str))
        finally:
            cur.close()
        return results

    return cur

def create_mysql_connection(**kwargs):
    """Create a connection.
    """
    try:
        cnx = mysql.connector.Connect(**kwargs)
        _LOGGER.debug("Created connection (%s).", cnx)
        return cnx
    except mysql.connector.Error as error:
        raise _errors.DatabaseError("Cannot connect to the server. "\
            "Error %s" % (str(error)), error.errno)

def destroy_mysql_connection(cnx):
    """Close the connection.
    """
    try:
        _LOGGER.debug("Destroying connection (%s).", cnx)
        cnx.disconnect()
    except Exception as error:
        raise _errors.DatabaseError("Error tyring to disconnect. "\
                                    "Error %s" % (str(error)))

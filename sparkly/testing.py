import json
import logging
import sys
import os
import shutil
from unittest import TestCase

from sparkly.exceptions import FixtureError
from sparkly import SparklyContext

if sys.version_info.major == 3:
    from http.client import HTTPConnection
else:
    from httplib import HTTPConnection

try:
    from cassandra.cluster import Cluster
except ImportError:
    pass

try:
    import pymysql as connector
except ImportError:
    try:
        import mysql.connector as connector
    except:
        pass


logger = logging.getLogger()


_test_context_cache = None


class SparklyTest(TestCase):
    """Base test for spark scrip tests.

    Initializes and shuts down Context specified in `context` param.

    Example:

        >>> class MyTestCase(SparklyTest):
        ...     def test(self):
        ...         self.assertDataFrameEqual(
        ...              self.hc.sql('SELECT 1 as one').collect(),
        ...              [{'one': 1}],
        ...         )
    """
    context = SparklyContext
    class_fixtures = []
    fixtures = []
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        super(SparklyTest, cls).setUpClass()

        # In case if project has a mix of SparklyTest and SparklyGlobalContextTest-based tests
        global _test_context_cache
        if _test_context_cache:
            logger.info('Found a global context, stopping it %r', _test_context_cache)
            _test_context_cache._sc.stop()
            _test_context_cache = None

        cls.hc = cls.context()

        for fixture in cls.class_fixtures:
            fixture.setup_data()

    @classmethod
    def tearDownClass(cls):
        cls.hc._sc.stop()
        super(SparklyTest, cls).tearDownClass()

        try:
            shutil.rmtree('metastore_db')
        except OSError:
            pass

        try:
            os.unlink('derby.log')
        except OSError:
            pass

        for fixture in cls.class_fixtures:
            fixture.teardown_data()

    def setUp(self):
        for fixture in self.fixtures:
            fixture.setup_data()

    def tearDown(self):
        for fixture in self.fixtures:
            fixture.teardown_data()

    def assertDataFrameEqual(self, actual_df, expected_data, fields=None, ordered=False):
        """Ensure that DataFrame has the right data inside.

        Args:
            actual_df (pyspark.sql.DataFrame|list[pyspark.sql.Row]): Dataframe to test data in.
            expected_data (list[dict]): Expected dataframe rows defined as dicts.
            fields (list[str]): Compare only certain fields.
            ordered (bool): Does order of rows matter?
        """
        if fields:
            actual_df = actual_df.select(*fields)

        actual_rows = actual_df.collect() if hasattr(actual_df, 'collect') else actual_df
        actual_data = [row.asDict(recursive=True) for row in actual_rows]

        if ordered:
            self.assertEqual(actual_data, expected_data)
        else:
            try:
                self.assertCountEqual(actual_data, expected_data)
            except AttributeError:
                self.assertItemsEqual(actual_data, expected_data)


class SparklyGlobalContextTest(SparklyTest):
    """Base test case that keeps a single instance for the given context class across all tests.

    Integration tests are slow, especially when you have to start/stop Spark context
    for each test case. This class allows you to reuse Spark context across multiple test cases.
    """
    @classmethod
    def setUpClass(cls):
        global _test_context_cache

        if _test_context_cache and cls.context == type(_test_context_cache):
            logger.info('Reusing the global context for %r', cls.context)
            hc = _test_context_cache
        else:
            if _test_context_cache:
                logger.info('Stopping the previous global context %r', _test_context_cache)
                _test_context_cache._sc.stop()

            logger.info('Starting the new global context for %r', cls.context)
            hc = _test_context_cache = cls.context()

        cls.hc = hc

        for fixture in cls.class_fixtures:
            fixture.setup_data()

    @classmethod
    def tearDownClass(cls):
        cls.hc.clearCache()

        for fixture in cls.class_fixtures:
            fixture.teardown_data()


class Fixture(object):
    """Base class for fixtures.

    Fixture is a term borrowed from Django tests,
    it's data loaded into database for integration testing.
    """

    def setup_data(self):
        """Method called to load data into database."""
        raise NotImplementedError()

    def teardown_data(self):
        """Method called to remove data from database which was loaded by `setup_data`."""
        raise NotImplementedError()

    def __enter__(self):
        self.setup_data()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.teardown_data()

    @classmethod
    def read_file(cls, path):
        with open(path) as f:
            data = f.read()
        return data


class CassandraFixture(Fixture):
    """Fixture to load data into cassandra.

    Notes:
        * Depends on cassandra-driver.

    Examples:

           >>> class MyTestCase(SparklyTest):
           ...      fixtures = [
           ...          CassandraFixture(
           ...              'cassandra.host',
           ...              absolute_path(__file__, 'resources', 'setup.cql'),
           ...              absolute_path(__file__, 'resources', 'teardown.cql'),
           ...          )
           ...      ]
           ...

           >>> class MyTestCase(SparklyTest):
           ...      data = CassandraFixture(
           ...          'cassandra.host',
           ...          absolute_path(__file__, 'resources', 'setup.cql'),
           ...          absolute_path(__file__, 'resources', 'teardown.cql'),
           ...      )
           ...      def setUp(self):
           ...          data.setup_data()
           ...      def tearDown(self):
           ...          data.teardown_data()
           ...

           >>> def test():
           ...     fixture = CassandraFixture(...)
           ...     with fixture:
           ...        test_stuff()
           ...
    """

    def __init__(self, host, setup_file, teardown_file):
        self.host = host
        self.setup_file = setup_file
        self.teardown_file = teardown_file

    def _execute(self, statements):
        cluster = Cluster([self.host])
        session = cluster.connect()
        for statement in statements.split(';'):
            if bool(statement.strip()):
                session.execute(statement.strip())

    def setup_data(self):
        self._execute(self.read_file(self.setup_file))

    def teardown_data(self):
        self._execute(self.read_file(self.teardown_file))


class ElasticFixture(Fixture):
    """Fixture for elastic integration tests.

    Notes:
     * Data upload uses bulk api.

    Examples:

           >>> class MyTestCase(SparklyTest):
           ...      fixtures = [
           ...          ElasticFixture(
           ...              'elastic.host',
           ...              'es_index',
           ...              'es_type',
           ...              '/path/to/mapping.json',
           ...              '/path/to/data.json',
           ...          )
           ...      ]
           ...
    """

    def __init__(self, host, es_index, es_type, mapping=None, data=None, port=None):
        self.host = host
        self.port = port or 9200
        self.es_index = es_index
        self.es_type = es_type
        self.mapping = mapping
        self.data = data

    def setup_data(self):
        if self.mapping:
            self._request(
                'PUT',
                '/{}'.format(self.es_index),
                json.dumps({
                    'settings': {
                        'index': {
                            'number_of_shards': 1,
                            'number_of_replicas': 1,
                        }
                    }
                }),
            )
            self._request(
                'PUT',
                '/{}/_mapping/{}'.format(self.es_index, self.es_type),
                self.read_file(self.mapping),
            )

        if self.data:
            self._request(
                'POST',
                '/_bulk',
                self.read_file(self.data),
            )
            self._request(
                'POST',
                '/_refresh',
            )

    def teardown_data(self):
        self._request(
            'DELETE',
            '/{}'.format(self.es_index),
        )

    def _request(self, method, url, body=None):
        connection = HTTPConnection(self.host, port=self.port)
        connection.request(method, url, body)
        response = connection.getresponse()
        if sys.version_info.major == 3:
            code = response.code
        else:
            code = response.status

        if code != 200:
            raise FixtureError('{}: {}'.format(code, response.read()))


class MysqlFixture(Fixture):
    """Base test class for mysql integration tests.

    Notes:
     * depends on PyMySql lib.

    Examples:

           >>> class MyTestCase(SparklyTest):
           ...      fixtures = [
           ...          MysqlFixture('mysql.host', 'user', 'password', '/path/to/data.sql')
           ...      ]
           ...      def test(self):
           ...          pass
           ...
    """

    def __init__(self, host, user, password=None, data=None, teardown=None):
        self.host = host
        self.user = user
        self.password = password
        self.data = data
        self.teardown = teardown

    def _execute(self, statements):
        ctx = connector.connect(
            user=self.user,
            password=self.password,
            host=self.host,
        )
        cursor = ctx.cursor()
        cursor.execute(statements)
        ctx.commit()
        cursor.close()
        ctx.close()

    def setup_data(self):
        self._execute(self.read_file(self.data))

    def teardown_data(self):
        self._execute(self.read_file(self.teardown))

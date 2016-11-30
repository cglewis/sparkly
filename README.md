## Sparkly

Helpers & syntax sugar for PySpark.


### Context definition

The library simplifies usage of spark packages and externals jars by allowing you 
to define their importation in code rather than when launching the pyspark process.
It was designed as a single place to define project-level dependencies and configuration.
`SparklyContext` is inherited from the `HiveContext`, so you can use it as a regular `HiveContext`.

```
import sparkly


class MyProjectContext(sparkly.SparklyContext):
    # Something that you can find on http://spark-packages.org/
    packages = [
        'org.elasticsearch:elasticsearch-spark_2.10:2.2.0',
    ]
    
    # Connect external UDFs/UDAFs 
    jars = [
        '/path/to/custom/jar/file.jar',
    ]
    
    # Customise Spark options
    options = {
        'spark.sql.shuffle.partitions': '1000',
    }
    

hc = MyProjectContext()

hc.read_ext.parquet('path/to/parquet/file')
```

### Accessing data sources

Examples below provide only the basic way of using DataFrame readers and writers,
it is always a good idea to check configuration options provided by the related spark package.

#### Cassandra

Package - http://spark-packages.org/package/datastax/spark-cassandra-connector  
Configuration - https://github.com/datastax/spark-cassandra-connector/blob/b1.5/doc/reference.md  
```
import sparkly


class MyProjectContext(sparkly.SparklyContext):
    packages = ['datastax:spark-cassandra-connector:1.5.0-M3-s_2.10']
    

hc = MyProjectContext()

# To read data
df = sparkly.read_ext.cassandra(hc, 'cassandra.host', 'db', 'table')

# To write data
df.write_ext.cassandra('cassandra.host', 'db', 'table')
```

#### CSV

Package - http://spark-packages.org/package/databricks/spark-csv  
Configuration - https://github.com/databricks/spark-csv#features  
```
import sparkly


class MyProjectContext(sparkly.SparklyContext):
    packages = ['com.databricks:spark-csv_2.10:1.4.0']


hc = MyProjectContext()

# To read data
df = hc.read_ext.csv(hc, 'path/to/the/csv/file.csv', header=True)

# To write data
df.write_ext.csv('path/to/the/csv/file.csv', header=False)

```

#### ElasticSearch

Package - http://spark-packages.org/package/elastic/elasticsearch-hadoop  
Configuration - https://www.elastic.co/guide/en/elasticsearch/hadoop/current/configuration.html  

```
import sparkly


class MyProjectContext(sparkly.SparklyContext):
    packages = ['org.elasticsearch:elasticsearch-spark_2.10:2.2.0']


hc = MyProjectContext()

# To read data
df = hc.read_ext.elastic(hc, 'elastic.host', 'index', 'type', fields=['title', 'views'])
    
# To write data
df.write_ext.elastic('elastic.host', 'index', 'type')
```

#### Mysql database

```
import sparkly

hc = SparklyContext()

df = hc.read_ext.mysql('localhost', 'database', 'table',
                       options={'user': 'root', 'password': 'pass'})
```


#### Generic reader

The main idea of the generic reader is to provide a unified way to define data sources.
The most popular use-case is to path urls as CLI arguments to your program, e.g.:
```
# To use a parquet file on S3 as an input
./my_program.py --input=parquet:s3://....

# To use a cassandra table as an input
./my_program.py --input=cassandra://...
```

Supported formats: 
```
import sparkly

hc = SparklyContext()

metastore_df = hc.read_ext.by_url('table://my_hive_metastore_table')
parquet_df = hc.read_ext.by_url('parquet:s3://some_bucket/some_parquet/')
csv_df = hc.read_ext.by_url('csv:s3://some_bucket/some.csv')
elastic_df = hc.read_ext.by_url('elastic://localhost/index_name/type_name?q=name:*Johhny*')
cassandra_df = hc.read_ext.by_url('cassandra://localhost/key_space/table_name?consistency=ONE')
mysql_df = hc.read_ext.by_url('mysql://localhost/db_name/table_name?user=root&password=pass')
```

### Utils for testing

```
from sparkly.test import MysqlFixture, SparklyTest

class MyTestCase(SparklyTest):
    ...
    fixtures = [
        MysqlFixture('mysql.host',
                     'user',
                     'password',
                     '/path/to/setup_data.sql',
                     '/path/to/remove_data.sql')
    ]
    ...
```


### Hql utils

Create and replace Hive metastore tables using Spark dataframes:
```
from sparkly import SparklyContext
# input
hc = SparklyContext()
df = hc.read_ext.by_url('parquet:s3://path/to/data/')
# operation
hc.hms.create_table(
     'new_shiny_table',
     df,
     location='s3://path/to/data/',
     partition_by=['partition', 'fields'],
     output_format='parquet'
)
new_df = hc.read_ext.by_url('table://new_shiny_table')
hc.hms.replace_table(
     'new_shiny_table',
     df,
     location='s3://path/to/data/',
     partition_by=['partition', 'fields'],
)
```

Operate on table attributes via python api, not sql queries:
```
from sparlke import SparklyContext
hc = SparklyContext()
hc.hms.table('my_table').set_property('last_update', '2016-01-01')
prop_value = hc.hms.table('my_table').get_property('last_update')
all_properties = hc.hms.table('my_table').get_all_properties()
```

### Documentation

#### Build
```
make docs
open docs/build/index.html
```

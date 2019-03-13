import sys

from flask import Flask
from flask_cors import CORS
import kin

import logging as log

from tippicserver.amqp_publisher import AmqpPublisher
from stellar_base.network import NETWORKS
from .encrypt import AESCipher


app = Flask(__name__)
CORS(app)

# set log level
log.getLogger().setLevel(log.INFO)

from flask_sqlalchemy import SQLAlchemy
from tippicserver import config, ssm, stellar

from .utils import increment_metric
increment_metric('server-starting')

# get seeds, channels from aws ssm:
base_seed, channel_seeds = ssm.get_stellar_credentials()
if not base_seed:
    log.error('could not get base seed - aborting')
    sys.exit(-1)

if channel_seeds is None:
    log.error('could not get channels seeds - aborting')
    sys.exit(-1)

# init sdk:
print('using kin-stellar sdk version: %s' % kin.version.__version__)
print("stellar horizon: %s" % config.STELLAR_HORIZON_URL)
# define an asset to forward to the SDK because sometimes we're using a custom issuer
from stellar_base.asset import Asset
kin_asset = Asset('KIN', config.STELLAR_KIN_ISSUER_ADDRESS)

if config.STELLAR_NETWORK != 'TESTNET':
    log.info('starting the sdk in a private network')
    network = 'CUSTOM'
    NETWORKS[network] = config.STELLAR_NETWORK
else:
    print('starting the sdk on the public testnet')
    network = config.STELLAR_NETWORK

app.kin_sdk = kin.SDK(secret_key=base_seed,
                      horizon_endpoint_uri=config.STELLAR_HORIZON_URL,
                      network=network,
                      channel_secret_keys=channel_seeds,
                      kin_asset=kin_asset)

# get (and print) the current balance for the account:
from stellar_base.keypair import Keypair
log.info('the current KIN balance on the base-seed: %s' % stellar.get_kin_balance(Keypair.from_seed(base_seed).address().decode()))
# get (and print) the current balance for the account:
log.info('the current XLM balance on the base-seed: %s' % stellar.get_xlm_balance(Keypair.from_seed(base_seed).address().decode()))

for channel in channel_seeds:
    address = Keypair.from_seed(channel).address().decode()
    print('the current XLM balance on channel (%s): %s' % (address, stellar.get_xlm_balance(address)))

# init encryption util
key, iv = ssm.get_encrpytion_creds()
app.encryption = AESCipher(key, iv)

# SQLAlchemy stuff:
# create an sqlalchemy engine with "autocommit" to tell sqlalchemy NOT to use un-needed transactions.
# see this: http://oddbird.net/2014/06/14/sqlalchemy-postgres-autocommit/
# and this: https://github.com/mitsuhiko/flask-sqlalchemy/pull/67
class MySQLAlchemy(SQLAlchemy):
    def apply_driver_hacks(self, app, info, options):
        options['isolation_level'] = 'AUTOCOMMIT'
        super(MySQLAlchemy, self).apply_driver_hacks(app, info, options)

app.config['SQLALCHEMY_DATABASE_URI'] = config.DB_CONNSTR

# SQLAlchemy timeouts
app.config['SQLALCHEMY_POOL_SIZE'] = 1000
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 5
app.config['SQLALCHEMY_MAX_OVERFLOW'] = 100
app.config['SQLALCHEMY_POOL_RECYCLE'] = 60*5

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if config.DEBUG:
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

if config.DEPLOYMENT_ENV in ['prod', 'stage']:
    print('starting sqlalchemy in autocommit mode')
    db = MySQLAlchemy(app)
else:
    db = SQLAlchemy(app)

#SQLAlchemy logging
#import logging
#logging.basicConfig()
#logging.getLogger('sqlalchemy').setLevel(logging.DEBUG)
#logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
#logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)

import tippicserver.views_private
import tippicserver.views_public
import redis
from rq import Queue

#redis:
app.redis = redis.StrictRedis(host=config.REDIS_ENDPOINT, port=config.REDIS_PORT, db=0)
# redis config sanity
app.redis.setex('temp-key', 1, 'temp-value')

# start the rq queue connection
app.rq_fast = Queue('tippicserver-%s-fast' % config.DEPLOYMENT_ENV, connection=redis.Redis(host=config.REDIS_ENDPOINT, port=config.REDIS_PORT, db=0), default_timeout=200)
app.rq_slow = Queue('tippicserver-%s-slow' % config.DEPLOYMENT_ENV, connection=redis.Redis(host=config.REDIS_ENDPOINT, port=config.REDIS_PORT, db=0), default_timeout=7200)

# useful prints:
state = 'enabled' if config.PHONE_VERIFICATION_ENABLED else 'disabled'
log.info('phone verification: %s' % state)
state = 'enabled' if config.AUTH_TOKEN_ENABLED else 'disabled'
log.info('auth token enabled: %s' % state)
state = 'enabled' if config.AUTH_TOKEN_ENFORCED else 'disabled'
log.info('auth token enforced: %s' % state)
state = 'enabled' if config.P2P_TRANSFERS_ENABLED else 'disabled'
log.info('p2p transfers: %s' % state)

# get the firebase service-account from ssm
service_account_file_path = ssm.write_service_account()

# init the firebase admin stuff
import firebase_admin
from firebase_admin import credentials
cred = credentials.Certificate(service_account_file_path)
firebase_admin.initialize_app(cred)
app.firebase_admin = firebase_admin

# figure out blocked prefixes - if this fail, crash the server
from ast import literal_eval
app.blocked_phone_prefixes = literal_eval(config.BLOCKED_PHONE_PREFIXES)
app.allowed_phone_prefixes = literal_eval(config.ALLOWED_PHONE_PREFIXES)
app.blocked_country_codes = literal_eval(config.BLOCKED_COUNTRY_CODES)

# initialize geoip instance
from geolite2 import geolite2
app.geoip_reader = geolite2.reader()

# print db creation statements
if config.DEBUG:
    from .utils import print_creation_statement
    print_creation_statement()
    pass
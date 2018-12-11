import json
import unittest
import uuid

import testing.postgresql
from stellar_base.keypair import Keypair
from stellar_base.address import Address

import tippicserver
from tippicserver import db

from tippicserver import stellar

import logging as log
log.getLogger().setLevel(log.INFO)


USER_ID_HEADER = "X-USERID"


class Tester(unittest.TestCase):

    #@mock.patch('redis.StrictRedis', mockredis.mock_redis_client)
    def setUp(self):
        #overwrite the db name, dont interfere with stage db data
        self.postgresql = testing.postgresql.Postgresql()
        tippicserver.app.config['SQLALCHEMY_DATABASE_URI'] = self.postgresql.url()
        tippicserver.app.testing = True
        #tippicserver.app.redis = redis.StrictRedis(host='0.0.0.0', port=6379, db=0) # doesnt play well with redis-lock
        self.app = tippicserver.app.test_client()
        db.drop_all()
        db.create_all()
        


    def tearDown(self):
        self.postgresql.stop()

    
    def test_onboard(self):
        """test onboarding scenarios"""

        #TODO ensure there's enough money in the test account to begin with

        userid = str(uuid.uuid4())
        resp = self.app.post('/user/register',
            data=json.dumps({
                            'user_id': str(userid),
                            'os': 'android',
                            'device_model': 'samsung8',
                            'device_id': '234234',
                            'time_zone': '05:00',
                            'token': 'fake_token',
                            'app_ver': '1.0'}),
            headers={},
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        # try to onboard user, should succeed

        print('####### onboarding user --------------')
        kp = Keypair.random()
        paddr = kp.address().decode()
        resp = self.app.post('/user/onboard',
            data=json.dumps({
                            'public_address': paddr}),
            headers={USER_ID_HEADER: str(userid)},
            content_type='application/json')

        print(json.loads(resp.data))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(15, stellar.get_kin_balance(paddr))

        # try onboarding again with the same user - should fail
        resp = self.app.post('/user/onboard',
            data=json.dumps({
                            'public_address': kp.address().decode()}),
            headers={USER_ID_HEADER: str(userid)},
            content_type='application/json')
        print(json.loads(resp.data))
        self.assertEqual(resp.status_code, 400)

        # try sending kin to that public address
        """ NEED TO ESTABLISH TRUST FIRST
        resp = self.app.post('/send-kin',
            data=json.dumps({
                            'public_address': kp.address().decode(),
                            'amount': 1}),
            headers={USER_ID_HEADER: str(userid)},
            content_type='application/json')
        print(json.loads(resp.data))
        self.assertEqual(resp.status_code, 200)
        """



if __name__ == '__main__':
    unittest.main()

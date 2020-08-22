import os,time,sys,logging
from pathlib import Path
import asyncio,time
# handler = logging.StreamHandler()
# formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
# handler.setFormatter(formatter)
# logger = logging.getLogger(__file__)
# logger.addHandler(handler)
# logger.setLevel(logging.DEBUG)
sys.path.append('../p2p')
# logger.info(os.getcwd(), sys.path)
BSEP=b'\n\n\n\n'
BSEP2=b'\t\n\t\n'
BSEP3=b'\r\r\r\r'
NODE_SLEEP_FOR=1

try:
    from .crypto import *
    from .p2p import *
    from .kad import *
except (ModuleNotFoundError,ImportError):
    from crypto import *
    from p2p import *
    from kad import *
from pathlib import Path
from functools import partial

# works better with tor?
import json
jsonify = json.dumps

# Start server

DEBUG = True
UPLOAD_DIR = 'uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# PORT_SPEAK = 8468
PORT_LISTEN = 5639

# Api Functions
from threading import Thread


NODES_PRIME = [("128.232.229.63",8467), ("68.66.241.111",8467)] 
#68.66.224.46

from pathlib import Path
home = str(Path.home())
KEYDIR = os.path.join(home,'.komrade','.keys')
if not os.path.exists(KEYDIR): os.makedirs(KEYDIR)



async def _getdb(self=None,port=PORT_LISTEN):
    from kademlia.network import Server

    if self: self.log('starting server..')

    import os
    if self: self.log(os.getcwd())
    node = Server() #fn='../p2p/data.db',log=(self.log if self else print)))

    if self: self.log('listening..')
    await node.listen(port)

    if self: self.log('bootstrapping server..')
    await node.bootstrap(NODES_PRIME)
    self.log('NODE:',node)
    return node

def logg(*x):
    print(*x)

class Api(object):
    def __init__(self,user=None,log=None):
        self.log = log if log is not None else logg
        self.username = user

    def private_key(self):
        if self.username:
            pass

    async def connect_forever(self,port=PORT_LISTEN,save_every=10):
        try:
            i = 0
            self._node = await self.connect(port=port)
            while True:
                if not i%60: self.log(f'Node status (tick {i}): {self._node}')
                if i and not i%save_every: await self.flush()
                i += 1
                await asyncio.sleep(NODE_SLEEP_FOR)
                # asyncio.sleep(0)
        except (asyncio.CancelledError,KeyboardInterrupt) as e:
            self.log('P2P node cancelled', e)
            await self.flush()
        finally:
            # when canceled, print that it finished
            self.log('P2P node shutting down')
            pass
        

    @property
    async def node(self):
        # while not hasattr(self,'_node'):
        #     self.log('[API] waiting forr connection...')
        #     await asyncio.sleep(1)
        # return self._node
        
        if not hasattr(self,'_node'):
            await self.connect()
        return self._node

    async def connect(self,port=PORT_LISTEN):
        self.log('connecting...')
        node = await _getdb(self,port)
        self.log(f'connect() has node {node}')
        self._node = node
        return node




    async def get(self,key_or_keys,decode_data=True):
        self.log(f'get({key_or_keys},decode_data={decode_data}) --> ...')
        async def _get():
            node=await self.node
            res=None
            if type(key_or_keys) in {list,tuple,dict}:
                keys = key_or_keys

                tasks=[]
                for key in keys:
                    val = await node.get(key)
                    task = self.decode_data(val) if decode_data else val
                    tasks.append(task)
                res = await asyncio.gather(*tasks)
            else:
                key=key_or_keys
                val = await node.get(key)
                res = await self.decode_data(val) if decode_data else val
                self.log('wtf is val =',val)
                self.log('wtf is res =',val)
            
            self.log(f'_get({key_or_keys}) --> {res}')
            return res
        return await _get()

    def encode_data(self,val,sep=BSEP,sep2=BSEP2,do_encrypt=True,receiver_pubkey=None,private_signature_key=None):
        """
        What do we want to store with
        
        1) [Encrypted payload:]
            1) Timestamp
            2) Public key of sender
            3) Public key of recipient
            4) AES-encrypted Value
        2) [Decryption tools]
            1) AES-decryption key
            2) AES decryption IV value
        5) Signature of value by author
        """
        import time
        timestamp=time.time()

        # check input
        if not receiver_pubkey: 
            self.log('we need a receiver !!')
            return None
        
        # convert val to bytes
        if type(val)!=bytes: val = bytes(val,'utf-8')
        value_bytes=base64.b64encode(val)

        # sign
        private_signature_key = private_signature_key if private_signature_key is not None else self.private_key
        signature = sign(value_bytes, private_signature_key)
        public_sender_key = private_signature_key.public_key()
        sender_pubkey_b = serialize_pubkey(public_sender_key)

        # Verify!
        authentic = verify_signature(signature, value_bytes, sender_pubkey_b)
        if not authentic:
            self.log('message is inauthentic for set??',authentic)
            return None

        # encrypt?
        receiver_pubkey_b = serialize_pubkey(receiver_pubkey)
        time_b=str(timestamp).encode()
        msg=value_bytes

        # whole binary package
        WDV = [
            time_b,
            sender_pubkey_b,
            receiver_pubkey_b,
            msg,
            signature
        ]
        payload = sep2.join(WDV)
        
        res = aes_rsa_encrypt(payload,receiver_pubkey)
        if res is None: return None
        payload_encr_aes, payload_encr_aes_key, payload_encr_aes_iv = res
        
        decryption_tools = sep2.join([
            payload_encr_aes_key,
            payload_encr_aes_iv
        ])

        final_packet = sep.join([
            payload_encr_aes,
            decryption_tools
        ])

        print('FINAL PACKET:',final_packet,type(final_packet))
        return final_packet

    

    async def decode_data(self,entire_packet_orig,sep=BSEP,private_key=None,sep2=BSEP2):
        if entire_packet_orig is None: return entire_packet_orig
        import binascii
        entire_packet = entire_packet_orig
        
        self.log('PACKED =',entire_packet,type(entire_packet))
        
        self.log('????',type(entire_packet))
        self.log(entire_packet)
        
        # get data
        try:
            encrypted_payload, decryption_tools = split_binary(entire_packet, sep=sep)  #entire_packet.split(sep)
            decryption_tools=split_binary(decryption_tools,sep=sep2)
        except AssertionError as e:

            self.log('!! decode_data() got incorrect format:',e)
            return entire_packet_orig 

        # ### FIRST LINE OF PROTECTION
        # # is the receiver's public id in our list of public IDs?
        # to_pub = load_pubkey(to_pub_b)
        # oktogo=False
        # CORRECT_PUB_KEY=None
        # CORRECT_PRIV_KEY=None
        # for privkey,pubkey in self.keys():
        #     if pubkey.public_numbers() == to_pub.public_numbers():
        #         oktogo=True
        #         CORRECT_PUB_KEY = pubkey
        #         CORRECT_PRIV_KEY = privkey
        #         break
        # if not oktogo: return None

        

        ### SECOND LINE OF PROTECTION
        # first try to decrypt sender to see if we have access to this
        # def _decrypt_aes_rsa(args):
        #     val_encr,val_encr_key,iv = args
        #     val = aes_rsa_decrypt(val_encr,val_encr_key,iv,CORRECT_PRIV_KEY)
        #     return val
        # from_pub_decr = _decrypt_rsa(*sender_encr)
        # if not from_pub_decr: return None
        # from_pub = load_pubkey(from_pub_b)
        

        ### NEW FIRST LINE: Try to decrypt!
        val=None
        for keyname,privkey,pubkey in self.keys():
            try:
                val = aes_rsa_decrypt(encrypted_payload,privkey,*decryption_tools)
                #self.log('decrypted =',val)
                break
            except ValueError as e:
                self.log(keyname,'did not work!') #,privkey,pubkey)
                pass
        if not val:
            self.log('Content not intended for us')
            return None

        #stop

        ### THIRD LINE: SIGNATURE VERIFICATION
        # can we decrypt signature?
        val_array = val.split(sep2)
        # self.log('val_array =',val_array)
        time_b,sender_pubkey_b,receiver_pubkey_b,msg,signature = val_array
        if not signature: return None
        sender_pubkey=load_pubkey(sender_pubkey_b)
        authentic = verify_signature(signature,msg,sender_pubkey)
        if not authentic: 
            self.log('inauthentic message!')
            return None


        # ### FOURTH LINE: CONTENT ENCRYPTION
        # if private_key is None:
        #     private_key=self.private_key_global
        
        # val_encr = base64.b64decode(val_encr)
        # val_encr_key = base64.b64decode(val_encr_key)
        # self.log(f"""decrypting
        # val_encr = {val_encr}
        # val_encr_key = {val_encr_key}
        # iv = {iv}
        # private_key = {private_key}
        # """)

        
        # val = _decrypt_aes()
        # self.log('val after decryption = ',val)
        # valdec = base64.b64decode(val)

        WDV={
            'time':float(time_b.decode()),
            'val':base64.b64decode(msg),
            'to':receiver_pubkey_b,
            'from':sender_pubkey_b,
            'sign':signature
        }

        # self.log('GOT WDV:',WDV)
        return WDV
        
        
         #,signature

    
    async def set(self,key_or_keys,value_or_values,private_signature_key=None,encode_data=True):
        self.log(f'api.set({key_or_keys}) --> {type(value_or_values)}')
        async def _set():
            # self.log('async _set()',self.node)
            # node=self.node
            #node=await _getdb(self)
            node=await self.node

            def proc(value):
                if encode_data:
                    return self.encode_data(value,private_signature_key=private_signature_key)
                return value

            if type(key_or_keys) in {list,tuple,dict}:
                keys = key_or_keys
                values = value_or_values
                assert len(keys)==len(values)
                tasks=[
                    node.set(
                        key,
                        proc(value)
                    )
                    for key,value in zip(keys,values)
                ]
                res = await asyncio.gather(*tasks)
                # self.log('RES?',res)
            else:
                key = key_or_keys
                value = value_or_values
                res = await node.set(key,proc(value))

            #node.stop()
            return res

        return await _set()

    async def get_json(self,key_or_keys,decode_data=True):
        
        def jsonize(entry):
            # self.log('jsonize!',entry)
            if not entry: return entry
            if not 'val' in entry: return entry
            val=entry['val']
            try:
                dat=json.loads(val) if val else val
            except UnicodeDecodeError:
                dat=val
            # self.log('dat??',dat)
            entry['val']=dat
            return entry

        def jsonize_res(res):
            # parse differently?
            if type(res)==list:
                jsonl=[jsonize(entry) for entry in res]
                return jsonl
            else:
                entry = res
                return jsonize(entry)

        # if key_or_keys.startsiwth('/post/'):
        res = await self.get(key_or_keys,decode_data=decode_data)
        self.log('get_json() got from get():',res)
        #self.log('get_json() got',res)
        if not res: return None
        return jsonize_res(res)
           


        

        


    async def set_json(self,key,value,private_signature_key=None,encode_data=True):
        value_json = jsonify(value)
        # self.log('OH NO!',sys.getsizeof(value_json))
        return await self.set(key,value_json,private_signature_key=None,encode_data=encode_data)

    async def has(self,key):
        val=await self.get(key)
        return val is not None


    ## PERSONS
    async def get_person(self,username):
        return await self.get('/person/'+username,decode_data=False)

    async def set_person(self,username,pem_public_key):
        # pem_public_key = save_public_key(public_key,return_instead=True)
        #obj = {'name':username, 'public_key':pem_public_key}
        # await self.set_json('/person/'+username,obj)
        await self.set('/person/'+username,pem_public_key,
                        private_signature_key=None,encode_data=False)






    ## Register
    async def register(self,name,passkey=None):
        # if not (name and passkey): return {'error':'Name and password needed'}
        person = await self.get_person(name)
        if person is not None:
            # try to log in
            self.log('my keys',self.keys.keys())
            if not name in self.keys: 
                return {'error':'Person already exists'}
            
            # test 3 conditions
            privkey=self.keys[name]
            pubkey=load_pubkey(person)

            if simple_lock_test(privkey,pubkey):
                self.username=name
                return {'success':'Logging back in...'}

        private_key = generate_rsa_key()
        public_key = private_key.public_key()
        pem_private_key = serialize_privkey(private_key, password=passkey)# save_private_key(private_key,password=passkey,return_instead=True)
        pem_public_key = serialize_pubkey(public_key)

        # save pub key in db
        await self.set_person(name,pem_public_key)
        # save priv key on hardware
        fn_privkey = os.path.join(KEYDIR,f'.{name}.key')

        self.log('priv key =',pem_private_key)
        write_key_b(pem_private_key, fn_privkey)

        # good
        return {'success':'Person created ...', 'username':name}
    

    def load_private_key(self,password):
        #if not self.app_storage.exists('_keys'): return {'error':'No login keys present on this device'}
        pem_private_key=self.app_storage.get('_keys').get('private')
        # self.log('my private key ====',pem_private_key)
        try:
            return {'success':load_privkey(pem_private_key,password)}
        except ValueError as e:
            self.log('!!',e)
        return {'error':'Incorrect password'}



    ## LOGIN
    async def login(self,name,passkey):
        # verify input
        if not (name and passkey):
            return {'error':'Name and password required'}

        # try to load private key
        private_key_dat = self.load_private_key(passkey)
        if 'error' in private_key_dat:
            return {'error':private_key_dat['error']}
        if not 'success' in private_key_dat:
            return {'error':'Incorrect password?'}
        self._private_key = private_key = private_key_dat['success']

        # see if user exists
        person = await self.get_person(name)
        # self.log(person)
        if person is None:
            return {'error':'Login failed'}

        # verify keys
        # self.log('got person =',person)
        person_public_key_pem = person['public_key']
        public_key = load_pubkey(person_public_key_pem) #load_public_key(person_public_key_pem.encode())
        self._public_key = real_public_key = private_key.public_key()

        #log('PUBLIC',public_key.public_numbers())
        #log('REAL PUBLIC',real_public_key.public_numbers())

        if public_key.public_numbers() != real_public_key.public_numbers():
            return {'error':'Keys do not match!'}
        return {'success':'Login successful', 'username':name}
        
    #@property
    def get_keys(self):
        res={}
        for priv_key_fn in os.listdir(KEYDIR):
            if (not priv_key_fn.startswith('.') or not priv_key_fn.endswith('.key')): continue
            fnfn = os.path.join(KEYDIR,priv_key_fn)
            print(fnfn)
            priv_key=load_privkey_fn(fnfn)
            #pub_key=priv_key.public_key()
            name_key= '.'.join(priv_key_fn.split('.')[1:-1])
            res[name_key] = priv_key
            self.log(f'[API] found key {name_key} and added to keychain')
        return res
            

    @property
    def keys(self): 
        if not hasattr(self,'_keys'): self._keys = self.get_keys()
        return self._keys
    


    async def append_json(self,key,data):
        self.log(f'appending to uri {key}')
        sofar=await self.get_json_val(key,decode_data=True)
        self.log(f'sofar = {sofar}')
        if sofar is None: sofar = []
        if type(sofar)!=list: sofar=[sofar]
        if type(data)!=list: data=[data]
        new=sofar + data
        if await self.set_json(key, new):
            return {'success':'Length increased to %s' % len(new)}
        return {'error':'Could not append json'}

    async def upload(self,filename,file_id=None, uri='/file/',uri_part='/part/'):
        import sys

        if not file_id: file_id = get_random_id()
        part_ids = []
        part_keys = []
        parts=[]
        PARTS=[]
        buffer_size=100
        for part in bytes_from_file(filename,chunksize=1024*2):
            part_id = get_random_id()
            part_ids.append(part_id)
            part_key='/part/'+part_id
            part_keys.append(part_key)
            parts.append(part)
            # PARTS.append(part)
            
            # self.log('part!:',sys.getsizeof(part))
            #self.set(part_key,part)

            if len(parts)>=buffer_size:
                # self.log('setting...')
                await self.set(part_keys,parts)
                part_keys=[]
                PARTS+=parts
                parts=[]

        # set all parts    
        #self.set(part_keys,PARTS)
        # self.log('# parts:',len(PARTS))
        if parts and part_keys:
            await self.set(part_keys, parts)

        # how many parts?
        # self.log('# pieces!',len(part_ids))

        file_store = {'ext':os.path.splitext(filename)[-1][1:], 'parts':part_ids}
        # self.log('FILE STORE??',file_store)
        await self.set_json(uri+file_id,file_store)
        
        # file_store['data'].seek(0)
        file_store['id']=file_id
        return file_store

    async def download(self,file_id):
        self.log('file_id =',file_id)
        file_store = await self.get_json_val('/file/'+file_id)
        self.log('file_store =',file_store)
        if file_store is None: return

        self.log('file_store!?',file_store)
        keys = ['/part/'+x for x in file_store['parts']]
        
        #time,pieces,pub,sign = await self.get_json_val(keys)
        pieces = await self.get_json_val(keys)
        self.log('pieces = ',pieces)
        file_store['parts_data']=pieces
        return file_store

    #def get_current_event_id(self):
    #    return self.get_json_val(self,'/current/event/id')

    # def get_uri(self):
    #     event_id = self.get_current_event_id()
    #     event_id=1 if event_id is None else int(event_id) 
    #     return f'/post/{event_id}'

    async def flush(self):
        self.log('saving back to db file...')
        node = await self.node
        node.storage.dump()
        self.log('DONE saving back to db file...')
        


    async def post(self,data,add_to_outbox=True):
        post_id=get_random_id()
        tasks = []
        self.log(f'post() added post {post_id}')
        task = self.set_json('/post/'+post_id, data)
        tasks.append(task)

        # res = await
        # if not res:
        #     self.log('!! error, couldn\'t set post json')
        #     return
        
        # ## add to inbox
        for channel in data.get('to_channels',[]):
            self.log('ADDING TO CHANNEL??',channel)
            task=self.append_json(f'/inbox/{channel}',post_id)
            tasks.append(task)

        ## add to outbox
        if add_to_outbox:
            un=data.get('author')
            if un:
                task = self.append_json(f'/outbox/{un}', post_id)
                tasks.append(task)

        self.log('gathering tasks')
        res = await asyncio.gather(*tasks)
        self.log('done with tasks')

        if res:
            asyncio.create_task(self.flush())
            return {'success':'Posted! %s' % post_id, 'post_id':post_id}
        return {'error':'Post failed'}

    async def get_json_val(self,uri,decode_data=True):
        res=await self.get_json(uri,decode_data=decode_data)
        self.log('get_json_val() got from get_json():',res)
        
        r=res
        if type(res) == dict:
            r=res.get('val',None) if res is not None else None
        elif type(res) == list:
            r=[x.get('val',None) for x in res if x is not None]
        elif type(res) == str:
            r=json.loads(res)
        self.log(f'get_json_val() --> {r}')
        return r

    async def get_post(self,post_id):
        return await self.get_json_val(post_id,decode_data=True)

    async def get_posts(self,uri='/inbox/earth'):
        # index = await self.get_json_val('/posts'+uri)
        self.log(f'api.get_posts(uri={uri}) --> ...')
        index = await self.get(uri,decode_data=True)
        if not index: return []

        self.log('first index =',index)
        index = json.loads(index)
        self.log('got index?',index,type(index))

        if index is None: return []
        if type(index)!=list: index=[index]
        
        index = [x for x in index if x is not None]

        ## get full json
        x = await self.get(['/post/'+x for x in index])
        return [y for y in x if y is not None]
        




## func

def bytes_from_file(filename,chunksize=8192):
    with open(filename, 'rb') as f:
        while True:
            piece = f.read(chunksize)  
            if not piece:
                break
            yield piece

def get_random_id():
    import uuid
    return uuid.uuid4().hex







def test_api():
    
    # api.set(['a','b','c'],[1,2,3])
    async def run():
        api = Api()
        # await api.connect()
        
        #await api.set_json('whattttt',{'aaaaa':12222})
        #await api.set_json('whattttt',[111])
        #await api.set_json('whattttt',[111])
        
        #val = await api.get_json('whattttt')
        
        server = await _getdb(api)
        await server.set('a',1)
        print(await server.get('a'))
        await asyncio.sleep(5)
        await server.set('a',2)

        print(await server.get('a'))
        await asyncio.sleep(5)

        await server.set('a',str([2,3,4,5]))
        print(await server.get('a'))
        await asyncio.sleep(5)

        val = await server.get('a')
        
        

        print(f'VAL = {val}')
        return val
    
    asyncio.run(run())


def test_basic():
    import asyncio
    from kademlia.network import Server

    #api = Api()
    
    # not working!
    #api.set_json('my key',{'a':'value'})

    async def run():
        # Create a node and start listening on port 5678
        node = Server()
        await node.listen(5678)

        # Bootstrap the node by connecting to other known nodes, in this case
        # replace 123.123.123.123 with the IP of another node and optionally
        # give as many ip/port combos as you can for other nodes.
        await node.bootstrap(NODES_PRIME)

        # set a value for the key "my-key" on the network
        await node.set("my-key", "my awesome value")
        await node.set("my-key", "my awesome value2")
        await node.set("my-key", "my awesome value3")


        # get the value associated with "my-key" from the network
        result = await node.get("my-key")

        print(result)
        return result

    res = asyncio.run(run())
    print('res = ',res)
    # res = asyncio.run(node.set(key,value))
    # print(res)

def test_provided_eg():
    import asyncio
    from kademlia.network import Server

    async def run():
        # Create a node and start listening on port 5678
        node = Server()
        await node.listen(5678)

        # Bootstrap the node by connecting to other known nodes, in this case
        # replace 123.123.123.123 with the IP of another node and optionally
        # give as many ip/port combos as you can for other nodes.
        await node.bootstrap(NODES_PRIME)

        # set a value for the key "my-key" on the network
        await node.set("my-key", "my awesome value")

        # get the value associated with "my-key" from the network
        result = await node.get("my-key")

        print(result)

    asyncio.run(run())



async def lonely_selfless_node():
    from api import Api,PORT_LISTEN
    API = Api()
    return await API.connect_forever(8467)


def boot_lonely_selfless_node(port=8467):
    API = Api()
    asyncio.run(API.connect_forever())
    

def init_entities(usernames = ['earth']):
    ## make global entity called earth
    
    #loop=asyncio.new_event_loop()

    async def register(username):
        API = Api() 
        #await API.connect_forever()
        #await API.register(username)
        print(API.keys)
        print('done')


    for un in usernames:
        asyncio.run(register(un))
    

def split_binary(data, sep=BSEP):
    seplen = len(BSEP)
    res=[]
    stack=None
    print('!!',data[:4],seplen,sep)

    cutoffs=[]
    for i in range(0, len(data)):
        seg=data[i:i+seplen]
        print(i,seg,sep,stack)
        if seg==sep:
            # split_piece = data[:i+seplen]
            print('!')
            cutoff_lasttime = cutoffs[-1][-1] if cutoffs and cutoffs else 0
            cutoff = (cutoff_lasttime-seplen, i)
            print(cutoff)
            cutoffs.append(cutoff)
            stack = data[cutoff[0] if cutoff[0]>0 else 0: cutoff[1]]
            print(stack)
            res += [stack]
            stack = None

    cutoff_lasttime = cutoffs[-1][-1] if cutoffs and cutoffs else 0
    print(cutoff_lasttime)
    stack = data[cutoff_lasttime+seplen :]
    res+=[stack]
    print('RES:',res)
    return res





if __name__=='__main__':
    #init_entities()

    res = split_binary(b'eeeehey||||whatsueep',b'||||')
    print(res)
import copy
import logging

from datetime import datetime
from pymongo import MongoClient
from typing import Dict, List, Optional, Tuple

from config import DEFAULT_SPACE
from utils import matchers
from utils.chat_data import ChatData
from utils.events import InvitationStatuses
from utils.matchers import normalize_username
from utils.spaces import SpaceConfig, MembershipStatus as MS

logger = logging.getLogger(__name__)


def make_multidict(items, keys) -> Dict[Tuple, List]:
    result = {}
    for item in items:
        if any(key_name not in item for key_name in keys):
            continue
        key = tuple(item[key_name] for key_name in keys)
        if key not in result:
            result[key] = []
        result[key].append(item)
    return result


class Database:
    def __init__(self, mongo_url, cache_ttl_seconds=10):
        self._setup_client(mongo_url=mongo_url)
        self._setup_collections()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache_time = datetime.now()
        self.update_cache(force=True)

    def _setup_client(self, mongo_url):
        self._mongo_client = MongoClient(mongo_url)
        self._mongo_db = self._mongo_client.get_default_database()

    def _setup_collections(self):
        self.mongo_users = self._mongo_db.get_collection('users')
        self.mongo_messages = self._mongo_db.get_collection('messages')
        self.mongo_coffee_pairs = self._mongo_db.get_collection('coffee_pairs')
        self.mongo_events = self._mongo_db.get_collection('events')
        # title (text), code (text), date (text), ... and many other fields
        self.mongo_participations = self._mongo_db.get_collection('event_participations')
        # username, code, status (INVITATION_STATUSES), invitor (username)
        self.mongo_peoplebook = self._mongo_db.get_collection('peoplebook')
        self.mongo_membership = self._mongo_db.get_collection('membership')
        self.message_queue = self._mongo_db.get_collection('message_queue')
        # (username: text, text: text, intent: text, fresh: bool)
        self.mongo_spaces = self._mongo_db.get_collection('spaces')
        self.mongo_chat_waiting_list = self._mongo_db.get_collection('chat_waiting_list')
        self.mongo_whois = self._mongo_db.get_collection('whois')
        self.mongo_chat_members = self._mongo_db.get_collection('chat_members')
        self.mongo_chats = self._mongo_db.get_collection('chats')

    def update_cache(self, force=False):
        if not force and (datetime.now() - self._cache_time).total_seconds() < self.cache_ttl_seconds:
            return
        self.update_spaces_cache()
        logger.info('updating database cache...')
        self._cache_time = datetime.now()

        self._cached_mongo_membership = {}
        for item in self.mongo_membership.find({}):
            if item.get('tg_id') is not None:
                self._cached_mongo_membership[(item['tg_id'], item['space'])] = item
            if item.get('username') is not None:
                self._cached_mongo_membership[(item['username'], item['space'])] = item

        participations = [
            p for p in self.mongo_participations.find({})
            if p.get('status') in InvitationStatuses.success_states()
        ]
        self._cached_mongo_participations = make_multidict(
            participations, keys=['username', 'space']
        )
        self._cached_mongo_participations.update(
            make_multidict(
                participations, keys=['tg_id', 'space']
            )
        )

    def update_spaces_cache(self):
        self._cached_spaces: Dict[str, SpaceConfig] = {
            record['key']: SpaceConfig.from_record(record, db=self)
            for record in self.mongo_spaces.find({})
        }

    def is_at_least_guest(self, user_object):
        return self.is_guest(user_object) or self.is_friend(user_object) \
               or self.is_member(user_object) or self.is_admin(user_object)

    def is_at_least_friend(self, user_object):
        return self.is_friend(user_object) or self.is_member(user_object) or self.is_admin(user_object)

    def is_at_least_member(self, user_object):
        return self.is_member(user_object) or self.is_admin(user_object)

    def is_admin(self, user_object):
        username = normalize_username(user_object.get('username') or 'anonymous')
        space_name = user_object.get('space') or DEFAULT_SPACE
        return self.username_is_admin(username=username, space_name=space_name)

    def has_at_least_level(self, user_object, level):
        user_status = self.get_top_status(user_object)
        return MS.is_at_least(user_status=user_status, level=level)

    def username_is_admin(self, username, space_name, uid=None):
        if space_name not in self._cached_spaces:
            return False
        space = self._cached_spaces[space_name]
        if username in space.admins:
            return True

        # now try user_id
        if uid is None and username.isdigit():
            uid, username = int(username), None

        if uid:
            if uid == space.owner_uid:
                return True
            if not username:
                user_object = self.find_user(space_name=space_name, username=None, tg_id=uid)
                if user_object and user_object.get('username') in space.admins:
                    return True
        return False

    def get_top_status(self, user_object):
        if self.is_admin(user_object=user_object):
            return MS.ADMIN
        elif self.is_member(user_object=user_object):
            return MS.MEMBER
        elif self.is_friend(user_object=user_object):
            return MS.FRIEND
        elif self.is_guest(user_object=user_object):
            return MS.GUEST
        else:
            return MS.NO_STATUS

    def _get_cached_mongo_membership(self, user_object) -> Dict:
        tg_id = user_object.get('tg_id') or 'anonymous'
        username = normalize_username(user_object.get('username') or 'anonymous')
        space = user_object.get('space') or DEFAULT_SPACE
        self.update_cache()
        mem = self._cached_mongo_membership.get((tg_id, space), {})
        if not mem:
            mem = self._cached_mongo_membership.get((username, space), {})
        return mem

    def is_member(self, user_object):
        mem = self._get_cached_mongo_membership(user_object)
        if mem.get('is_member'):
            return True
        if mem.get('is_member'):
            return True
        return False

    def is_friend(self, user_object):
        mem = self._get_cached_mongo_membership(user_object)
        if mem.get('is_member'):
            return True
        if mem.get('is_friend'):
            return True
        return False

    def is_guest(self, user_object):
        mem = self._get_cached_mongo_membership(user_object)

        tg_id = normalize_username(user_object.get('tg_id') or 'anonymous')
        username = normalize_username(user_object.get('username') or 'anonymous')
        space = user_object.get('space') or DEFAULT_SPACE

        if mem.get('is_guest'):
            return True
        if mem.get('is_friend'):
            return True
        if mem.get('is_member'):
            return True
        if (tg_id, space) in self._cached_mongo_participations:
            return True
        if (username, space) in self._cached_mongo_participations:
            return True
        return False

    def get_space_for_user(self, user_object) -> SpaceConfig:
        space_name = user_object['space']
        return self.get_space(space_name=space_name)

    def get_space(self, space_name) -> SpaceConfig:
        self.update_cache()
        return self._cached_spaces.get(space_name)

    @property
    def all_spaces(self) -> Dict[str, SpaceConfig]:
        self.update_cache()
        return copy.copy(self._cached_spaces)

    @property
    def db(self):
        return self._mongo_db

    def update_user_object(self, username_or_id, space_name, change, use_id=None):
        filters = {
            'space': space_name,
        }
        if use_id is True:
            filters['tg_id'] = username_or_id
        elif use_id is False:
            filters['username'] = username_or_id
        else:
            # choose the key based on the data type
            if isinstance(username_or_id, str) and not username_or_id.isnumeric():
                filters['username'] = username_or_id
            else:
                filters['tg_id'] = username_or_id
        self.mongo_users.update_one(filters, change or {})

    def add_member(self, tg_id, space_name):
        self.mongo_membership.update_one(
            {'tg_id': tg_id, 'space': space_name},
            {'$set': {'is_member': True}},
            upsert=True
        )

    def add_friend(self, tg_id, space_name):
        self.mongo_membership.update_one(
            {'tg_id': tg_id, 'space': space_name},
            {'$set': {'is_friend': True}},
            upsert=True
        )

    def add_guest(self, tg_id, space_name):
        self.mongo_membership.update_one(
            {'tg_id': tg_id, 'space': space_name},
            {'$set': {'is_guest': True}},
            upsert=True
        )

    def get_chats_for_space(self, space_name) -> List[ChatData]:
        return [
            ChatData.from_record(record=record, chat_id=None, space=space_name)
            for record in self.mongo_chats.find({'space': space_name})
        ]

    def get_chat(self, space_name, chat_id) -> Optional[ChatData]:
        record = self.mongo_chats.find_one({'space': space_name, 'chat_id': chat_id})
        if record:
            return ChatData.from_record(record=record, chat_id=chat_id, space=space_name)

    def find_peoplebook_profile(self, space_name, username=None, tg_id=None) -> Optional[Dict]:
        if not username and not tg_id:
            return
        the_profile = None
        if tg_id:
            if isinstance(tg_id, str) and tg_id.isnumeric():
                tg_id = int(tg_id)
            the_profile = self.mongo_peoplebook.find_one(
                {'tg_id': tg_id, 'space': space_name}
            )
        if username and not the_profile:
            the_profile = self.mongo_peoplebook.find_one(
                {'username': username, 'space': space_name}
            )
        return the_profile

    def update_peoplebook_profile(
            self, space_name, username=None, tg_id=None,

    ):
        # todo: complete it and use in scenarios
        pass

    def find_user(self, space_name, username, tg_id) -> Optional[Dict]:
        result = None
        if username:
            result = self.mongo_users.find_one(
                {'username': username, 'space': space_name}
            )
        if tg_id and not result:
            result = self.mongo_users.find_one(
                {'tg_id': tg_id, 'space': space_name}
            )
        return result

    def find_invitation(self, space_name, event_code, username, tg_id) -> Optional[Dict]:
        the_invitation = None
        if not tg_id:
            target_user = self.find_user(space_name=space_name, username=username, tg_id=None)
            tg_id = (target_user or {}).get('tg_id')

        if username:
            the_invitation = self.mongo_participations.find_one(
                {'username': username, 'code': event_code, 'space': space_name}
            )
        if tg_id and not the_invitation:
            the_invitation = self.mongo_participations.find_one(
                {'tg_id': tg_id, 'code': event_code, 'space': space_name}
            )
        return the_invitation

    def find_membership(self, space_name, username, tg_id) -> Optional[Dict]:
        result = None
        if username:
            result = self.mongo_membership.find_one(
                {'username': username, 'space': space_name}
            )
        if tg_id and not result:
            result = self.mongo_membership.find_one(
                {'tg_id': tg_id, 'space': space_name}
            )
        return result

    def update_participation(self, space_name, username, tg_id, event_code, the_update):
        """ Update a participation - and its username or tg_id, if needed. Insert one, if needed."""
        if not username and not tg_id:
            return
        if not tg_id:
            target_user = self.find_user(space_name=space_name, username=username, tg_id=None)
            tg_id = (target_user or {}).get('tg_id')

        the_update = copy.deepcopy(the_update)
        if username:
            the_update['username'] = username
        if tg_id:
            the_update['tg_id'] = tg_id

        p = self.find_invitation(space_name=space_name, username=username, tg_id=tg_id, event_code=event_code)
        if p:
            self.mongo_participations.update_one({'_id': p.get('_id')}, {'$set': the_update})
        else:
            the_update.update({
                'space': space_name,
                'code': event_code,
            })
            self.mongo_participations.insert_one(the_update)

    def where_user_is_admin(self, username, tg_id) -> List[SpaceConfig]:
        result = []
        for space in self._cached_spaces.values():
            if tg_id and tg_id == space.owner_uid:
                result.append(space)
                continue
            if username and username == space.owner_username:
                result.append(space)
                continue
            if username and username in space.admins:
                result.append(space)
                continue
        return result


class LoggedMessage:
    def __init__(
            self,
            text, user_id, from_user, database: Database,
            space_name, username=None, intent=None, meta=None,
            chat_id=None,
    ):
        self.text = text
        self.user_id = user_id
        self.chat_id = chat_id
        self.from_user = from_user
        self.space_name = space_name
        self.timestamp = str(datetime.utcnow())
        self.username = username
        self.intent = intent
        self.meta = meta

        self.mongo_collection = database.mongo_messages

    def save(self):
        self.mongo_collection.insert_one(self.to_dict())

    def to_dict(self):
        result = {
            'text': self.text,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'from_user': self.from_user,
            'timestamp': self.timestamp,
            'space': self.space_name,
        }
        if self.username is not None:
            result['username'] = matchers.normalize_username(self.username)
        if self.intent is not None:
            result['intent'] = self.intent
        if self.meta is not None:
            result['meta'] = self.meta
        return result


def get_or_insert_user(space_name, tg_user=None, tg_uid=None, database: Database = None):
    # todo: make user object a class
    if tg_user is not None:
        uid = tg_user.id
    elif tg_uid is not None:
        uid = tg_uid
    else:
        return None
    assert database is not None
    found = database.mongo_users.find_one({'tg_id': uid, 'space': space_name})
    if found is not None:
        if tg_user is not None and found.get('username') != matchers.normalize_username(tg_user.username):
            database.mongo_users.update_many(
                {'tg_id': uid},
                {'$set': {'username': matchers.normalize_username(tg_user.username)}}
            )
            database.mongo_membership.update_many(
                {'tg_id': uid},
                {'$set': {'username': matchers.normalize_username(tg_user.username)}}
            )
            database.mongo_peoplebook.update_many(
                {'tg_id': uid},
                {'$set': {'username': matchers.normalize_username(tg_user.username)}}
            )
            database.mongo_participations.update_many(
                {'tg_id': uid},
                {'$set': {'username': matchers.normalize_username(tg_user.username)}}
            )
            found = database.mongo_users.find_one({'tg_id': uid, 'space': space_name})
        return found
    if tg_user is None:
        return ValueError('User should be created, but telegram user object was not provided.')
    new_user = dict(
        tg_id=tg_user.id,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        username=matchers.normalize_username(tg_user.username),
        wants_next_coffee=False,
        space=space_name,
    )
    database.mongo_users.insert_one(new_user)
    return new_user

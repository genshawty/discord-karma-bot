from karma_dc.create_db import User, Base, Log
import json, os
from logging import Logger
from datetime import datetime, timedelta
from sqlalchemy import and_
from sqlalchemy.orm import Session
from typing import List
# roles = json.load(open(os.path.join(os.path.dirname(__file__), "roles.json")))
# settings = json.load(open(os.path.join(os.path.dirname(__file__), "settings.json")))
hour = timedelta(hours=1)

def get_action_info(text: str):
    '''
    Returns (action_id, action input, points) 
    points before multiplier
    '''
    actions = json.load(open(os.path.join(os.path.dirname(__file__), "actions.json")))["actions"]
    triggers = actions["trigger"]
    includes = actions["include"]

    for t in triggers:
        if text.lower() == t:
            return "trigger", t, triggers[t]["points"]

    for inc in includes:
            if inc in text.lower():
                return "include", inc, includes[inc]["points"]

    return "not action", "not input", 0

def create_new_user(user_id:int, user_name:str, s: Session):
    user = User(user_id=user_id, username=user_name, points=0, rolename=get_role_by_points(0)[0])
    return user

def get_role_by_points(points: int):
    roles = json.load(open(os.path.join(os.path.dirname(__file__), "roles.json")))

    for role in roles:
        if points <= roles[role]["upper_bound"]:
            return role, roles[role]["factor"]
    return role, roles[role]["factor"]

def get_role_id_dict():
    roles = json.load(open(os.path.join(os.path.dirname(__file__), "roles.json")))
    ans = dict()
    for role in roles:
        ans[role] = roles[role]["id"]
    return ans


def get_role_id(rolename: str):
    roles = json.load(open(os.path.join(os.path.dirname(__file__), "roles.json")))

    for role in roles:
        if rolename == role:
            return roles[role]["id"]

def get_user_by_user_id(user_id: int, s: Session):
    user = s.query(User).filter(User.user_id == user_id).all()

    if len(user) == 0:
        return None
    return user[0]

def check_intervals(logger: Logger, helper_id: int, helper_name: str, user_id: int, user_name: str, time: datetime, is_thank_back: bool, s: Session):
    intervals = json.load(open(os.path.join(os.path.dirname(__file__), "intervals.json")))
    # start from checking how many people has thanked user in last period
    period = intervals["thank_others"]["period"]
    num = intervals["thank_others"]["num"]
    req_time = time - num * hour

    ans = s.query(Log).filter(
        and_(
            Log.time > req_time,
            Log.user_id == user_id
        )).all()
    if len(ans) > num:
        logger.info("name: {} id: {} - thanked more than {} users in last {} hours THANK_OTHERS".format(user_name, user_id, num, period))
        return False

    # check if this user already thanked this helper in last period hours
    period = intervals["thank_exact_user"]["period"]
    num = intervals["thank_exact_user"]["num"]
    req_time = time - num * hour

    ans = s.query(Log).filter(
        and_(
            Log.time > req_time, 
            Log.user_id == user_id,
            Log.helper_id == helper_id
        )).all()
    if len(ans) > num:
        logger.info("name: {} id: {} - thanked helper {}:{} more than {} times in last {} hours THANK_EXACT".format(user_name, user_id, helper_id, helper_name, num, period))
        return False

    # check for thank_back
    if is_thank_back:
        period = intervals["thank_back"]["period"]
        num = intervals["thank_back"]["num"]
        req_time = time - num * hour

        ans = s.query(Log).filter(
            and_(
                Log.time > req_time,
                Log.user_id == user_id,
                Log.thank_back == True
            )).all()
        print("================", ans, "=====================")
        if len(ans) >= num:
            logger.info("name: {} id: {} - thanked more than {} users in last {} hours THANK_BACK".format(user_name, user_id, num, period))
            return False

    return True

def update_helper(helper: User, s: Session):
    s.add(helper)
    s.commit()

def add_points(logger: Logger, msg_id:int, helper_id: int, helper_name: str, user_id: int, user_name: str, channel_id, channel_name, points_change: int, action_id: str, action_input: str, is_thank_back: bool, time: datetime, s: Session) -> Log:
    '''
    points change before multiplier
    1) Checks if the helper is in the db
    2) Adds new helper if not
    3) Adds already calculated points
    4) Changes the role if required
    5) Adds row to log table
    '''
    # checking if helper is already in db
    helpers = s.query(User).filter(User.user_id == helper_id).all()
    helper = None
    ok = False # flag True - good with anti-grind system, False - bad with anti-grind

    if len(helpers) == 0:
        logger.info("name: {} id: {} - new helper".format(helper_name, helper_id))
        helper = create_new_user(user_id=helper_id, user_name=helper_name, s=s)
        ok = True
    else:
        helper = helpers[0]

        ok = check_intervals(logger, helper_id, helper_name, user_id, user_name, time, is_thank_back, s)

    if not ok:
        return 
    _, mul = get_role_by_points(helper.points)
    points_change *= mul
    helper.points += points_change

    new_role, _ = get_role_by_points(helper.points)

    role_changed = False
    if helper.rolename != new_role:
        helper.rolename = new_role
        role_changed = True

    if helper.username != helper_name:
        logger.info("name: {} id: {} - changed name from {}".format(helper_name, helper_id, helper.username))
        helper.username = helper_name
    s.add(helper)

    # adding logging row
    log_row = Log(msg_id=msg_id, helper_id=helper_id, helper_name=helper_name, user_id=user_id, user_name=user_name, channel_id=channel_id, channel_name=channel_name, action_id=action_id, action_input=action_input, points_change=points_change, new_points_balance=helper.points, thank_back=is_thank_back, role_changed=role_changed, time=time)
    s.add(log_row)
    s.commit()

    return log_row.to_string().format(helper.rolename), role_changed

def thank_back_check(msg_id: int, user_id: int, s: Session):
    ans = s.query(Log).filter(
        and_(
            Log.msg_id == msg_id,
            Log.helper_id == user_id
        )
    ).all()
    if len(ans) == 0:
        return False
    return True
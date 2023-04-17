from karma_dc.create_db import User, Base, Log
import json, os
from logging import Logger
from datetime import datetime, timedelta
from sqlalchemy import and_
from sqlalchemy.orm import Session
from karma_dc.karma import get_user_by_user_id, create_new_user, get_role_by_points

def export_users(s: Session):
    users = s.query(User).all()
    columns = ",".join(["user_id", "username", "rolename", "points"])

    users_string = "\n".join(map(lambda x: x.to_csv(), users))
    ans = columns + "\n" + users_string

    with open("data/users.csv", "w", encoding="utf8") as f:
        f.write(ans)

def export_log(s: Session):
    logs = s.query(Log).all()
    columns = ",".join(["message_id", "helper_id", "helper_name", "user_id", "user_name", "channel_id", "channel_name", "action_id", "action_input", "points_change", "new_points_balance",
                            "thank_back", "cancelled", "role_changed", "time"])

    logs_string = "\n".join(map(lambda x: x.to_csv(), logs))
    ans = columns + "\n" + logs_string

    with open("data/logs.csv", "w", encoding="utf8") as f:
        f.write(ans)

def get_log_channel():
    return json.load(open(os.path.join(os.path.dirname(__file__), "admins.json")))["log_channel"]

def if_admin_command(channel_id: int, author_id: int):
    return (channel_id in json.load(open(os.path.join(os.path.dirname(__file__), "admins.json")))["admin_channels"]) and if_admin(author_id)

def if_admin(user_id: int):
    return True
    admins = admin_list()
    return str(user_id) in admins

def admin_list():
    return json.load(open(os.path.join(os.path.dirname(__file__), "admins.json")))["admins"]

def leaderboard(s: Session):
    ans = s.query(User).order_by(User.points.desc())
    return ["{}: {}".format(user.username, user.points) for user in ans]

def cancel_action(message_id: int, s: Session):
    ans = s.query(Log).filter(Log.msg_id == message_id).all()[0]
    ans.cancelled = True

    helper_id = ans.helper_id
    change = ans.points_change

    helper = s.query(User).filter(User.user_id == helper_id).all()[0]
    helper.points -= change

    s.add(ans)
    s.add(helper)
    s.commit()

def show_user(user: User):
    return user

def add_points(user: User, n: int):
    user.points += n
    user.rolename = get_role_by_points(user.points)[0]
    return user

def sub_points(user: User, n: int):
    user.points -= n
    user.rolename = get_role_by_points(user.points)[0]
    return user

def set_points(user: User, n: int):
    user.points = n
    user.rolename = get_role_by_points(user.points)[0]
    return user

def admin_comand(action, user_name, user_id, num, s: Session) -> bool:
    user = get_user_by_user_id(user_id=user_id, s=s)
    if user is None:
        user = create_new_user(user_id=user_id, user_name=user_name, s=s)

    if num is not None:
        num = int(num)

    if action == "show":
        user = show_user(user)
        ans = user.to_string()
    elif action == "add":
        user = add_points(user, num)
        ans = "SUCCESFULLY ADDED POINTS " + user.to_string()
    elif action == "sub":
        user = sub_points(user, num)
        ans = "SUCCESFULLY SUBSTRACTED POINTS " + user.to_string()
    elif action == "set":
        user = set_points(user, num)
        ans = f"SUCCESFULLY SET POINTS " + user.to_string()

    s.add(user)
    s.commit()
    return ans
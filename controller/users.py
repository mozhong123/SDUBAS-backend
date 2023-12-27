import base64
import datetime
import json
import random
import string
import uuid
from io import BytesIO
from service.file import RSAModel
import requests
from captcha.image import ImageCaptcha
from fastapi import APIRouter, HTTPException
from fastapi import Request, Header, Depends
from Celery.add_operation import add_operation
from Celery.send_email import send_email
from model.db import session_db, user_information_db
from service.permissions import permissionModel
from service.user import UserModel, SessionModel, UserinfoModel, OperationModel, CaptchaModel
from type.functions import block_chains_login, block_chains_get
from type.functions import search_son_user, get_email_token, get_user_id, get_user_information, make_parameters, \
    get_user_name, extract_word_between, get_time_now, block_chains_information, decrypt_aes_key_with_rsa, oj_bind_func
from type.page import page
from type.permissions import create_user_role_base
from type.user import user_info_interface, \
    session_interface, email_interface, password_interface, user_add_interface, admin_user_add_interface, \
    login_interface, \
    captcha_interface, user_interface, reason_interface, user_add_batch_interface, oj_login_interface
from utils.auth_login import auth_login, auth_not_login, oj_login, oj_not_login
from utils.auth_permission import auth_permission_default
from utils.response import user_standard_response, page_response, makePageResult

users_router = APIRouter()
user_model = UserModel()
session_model = SessionModel()
user_info_model = UserinfoModel()
operation_model = OperationModel()
captcha_model = CaptchaModel()
permission_model = permissionModel()
RSA_model = RSAModel()
dtype_mapping = {
    'username': str,
    'password': str,
    'email': str,
    'card_id': str,
    'realname': str,
    'gender': int,
    'enrollment_dt': datetime.date,
    'graduation_dt': datetime.date
}


# 管理员输入一堆信息添加一个用户
@users_router.post("/user_add")
@user_standard_response
async def user_add(user_information: admin_user_add_interface, request: Request,
                   session=Depends(auth_login)):
    user = user_add_interface(username=user_information.username, password=user_information.password,
                              email=user_information.email, card_id=user_information.card_id)
    result = await user_unique_verify(user)  # 验证用户各项信息是否已存在
    ans = json.loads(result.body)
    if ans['code'] != 0:
        return ans
    user_id = user_model.add_user(user)  # 在user表里添加用户
    if user_information.class_id is not None and user_information.major_id is not None:
        user_info = user_info_interface(user_id=user_id, realname=user_information.realname,
                                        gender=user_information.gender,
                                        enrollment_dt=user_information.enrollment_dt,
                                        graduation_dt=user_information.graduation_dt,
                                        major_id=user_information.major_id, class_id=user_information.class_id)
    elif user_information.class_id is None and user_information.major_id is not None:
        user_info = user_info_interface(user_id=user_id, realname=user_information.realname,
                                        gender=user_information.gender,
                                        enrollment_dt=user_information.enrollment_dt,
                                        graduation_dt=user_information.graduation_dt,
                                        major_id=user_information.major_id)
    elif user_information.class_id is not None and user_information.major_id is None:
        user_info = user_info_interface(user_id=user_id, realname=user_information.realname,
                                        gender=user_information.gender,
                                        enrollment_dt=user_information.enrollment_dt,
                                        graduation_dt=user_information.graduation_dt,
                                        class_id=user_information.class_id)
    else:
        user_info = user_info_interface(user_id=user_id, realname=user_information.realname,
                                        gender=user_information.gender,
                                        enrollment_dt=user_information.enrollment_dt,
                                        graduation_dt=user_information.graduation_dt)
    user_info_model.add_userinfo(user_info)  # 在user_info表中添加用户
    permission_model.add_user_role(create_user_role_base(role_id=user_information.role_id, user_id=user_id))  # 为其分配一个角色
    parameters = await make_parameters(request)
    add_operation.delay(0, user_id, '添加用户', f"用户{session['user_id']}于xxx添加用户{user_id}",
                        parameters, session['user_id'])
    return {'message': '添加成功', 'data': True, 'code': 0}


# 管理员通过导入一个文件批量添加用户
@users_router.post("/user_add_batch")
@user_standard_response
async def user_add_all(request: Request, information: user_add_batch_interface, session=Depends(auth_login)):
    user = []
    user_info = []
    nums = len(information.information_list)
    for i in range(nums):
        user_key = ['用户名', '密码', '邮箱', '学号']
        user_info_key = ['姓名', '性别', '入学时间', '毕业时间']
        temp = {key: information.information_list[i][key] for key in user_key if key in information.information_list[i]}
        temp['username'] = temp.pop('用户名')
        temp['password'] = temp.pop('密码')
        temp['email'] = temp.pop('邮箱')
        temp['card_id'] = temp.pop('学号')
        user_data = user_add_interface(**temp)
        result = await user_unique_verify(user_data)  # 验证要添加的用户各项信息是否存在
        ans = json.loads(result.body)
        if ans['code'] != 0:
            ans['message'] = '第' + str(i + 1) + '位' + ans['message']  # 报出第几位有问题
            return ans
        user.append(user_data)
        temp = {key: information.information_list[i][key] for key in user_info_key if
                key in information.information_list[i]}
        temp['realname'] = temp.pop('姓名')
        temp['gender'] = temp.pop('性别')
        temp['enrollment_dt'] = temp.pop('入学时间')
        temp['graduation_dt'] = temp.pop('毕业时间')
        user_info_data = user_info_interface(**temp)
        user_info.append(user_info_data)
    user_id_list = user_model.add_all_user(user)  # 添加所有的user得到user_id_list
    user_info_model.add_all_user_info(user_info, user_id_list)  # 添加所有的user_info
    permission_model.add_all_user_role(information.role_id, user_id_list)  # 都分配一个默认角色
    parameters = await make_parameters(request)
    add_operation.delay(0, None, '批量添加用户', f"用户{session['user_id']}于xxx通过上传文件批量添加{nums}名用户",
                        parameters,
                        session['user_id'])
    return {'message': '添加成功', 'data': True, 'code': 0}


# 以分页形式查看管理员所能操作的所有用户
@users_router.get("/user_view")
@page_response
async def user_view(pageNow: int, pageSize: int, request: Request, session=Depends(auth_permission_default)):
    Page = page(pageSize=pageSize, pageNow=pageNow)
    user_list = search_son_user(request)  # 查看当前用户创建的所有子用户
    result = {'rows': None}
    if user_list != []:
        user_data = []
        for user_id in user_list:
            name = user_model.get_name_by_user_id(user_id)
            temp = user_interface(username=name[0], realname=name[1])
            user_data.append(temp)
        result = makePageResult(Page, len(user_list), user_data)  # 以分页形式返回
    parameters = await make_parameters(request)
    add_operation.delay(0, None, '查看用户', f"用户{session['user_id']}于xxx查看所有用户", parameters,
                        session['user_id'])
    return {'message': '人员如下', "data": result, "code": 0}


# 管理员根据user_id封禁人员
@users_router.put("/user_ban/{user_id}")
@user_standard_response
async def user_ban(request: Request, user_id: int, reason: reason_interface,
                   session=Depends(auth_login)):
    if user_id == session['user_id']:
        return {'message': '不能封禁自己', 'data': False, 'code': 4}
    exist_user = user_model.get_user_status_by_user_id(user_id)  # 查询用户的帐号状态
    if exist_user is None:  # 没有该用户
        return {'message': '没有该用户', 'data': False, 'code': 1}
    if exist_user[0] == 2:  # 账号已注销
        return {'message': '账号已注销', 'data': False, 'code': 2}
    elif exist_user[0] == 3:  # 账号已被封禁
        return {'message': '账号已被封禁', 'data': False, 'code': 3}
    id = user_model.update_user_status(user_id, 3)  # 将用户封禁
    parameters = await make_parameters(request)
    add_operation.delay(0, id, '封禁用户', f"用户{user_id}由于{reason.reason}被用户{session['user_id']}于xxx封禁",
                        parameters,
                        session['user_id'])
    return {'message': '封禁成功', 'data': True, 'code': 0}


# 管理员根据user_id解封人员
@users_router.put("/user_relieve/{user_id}")
@user_standard_response
async def user_relieve(request: Request, user_id: int, reason: reason_interface,
                       session=Depends(auth_permission_default)):
    exist_user = user_model.get_user_status_by_user_id(user_id)
    if exist_user is None:  # 没有该用户
        return {'message': '没有该用户', 'data': False, 'code': 1}
    if exist_user[0] == 2:  # 账号已注销
        return {'message': '账号已注销', 'data': False, 'code': 2}
    elif exist_user[0] == 0 or exist_user[0] == 1:  # 账号未被封禁
        return {'message': '账号未被封禁', 'data': False, 'code': 3}
    id = user_model.update_user_status(user_id, 1)  # 解封账号
    parameters = await make_parameters(request)
    add_operation.delay(0, id, '解封用户', f"用户{user_id}由于{reason.reason}被{session['user_id']}于xxx解封",
                        parameters,
                        session['user_id'])
    return {'message': '解封成功', 'data': True, 'code': 0}


# 验证用户用户名，邮箱，学号的唯一性
@users_router.post("/unique_verify")
@user_standard_response
async def user_unique_verify(reg_data: user_add_interface):
    if reg_data.username is not None:  # 验证用户名唯一性
        exist_username = user_model.get_user_status_by_username(reg_data.username)
        if exist_username is not None:
            return {'message': '用户名已存在', 'code': 1, 'data': False}
    if reg_data.email is not None:  # 验证邮箱唯一性
        exist_email = user_model.get_user_status_by_email(reg_data.email)
        if exist_email is not None:
            return {'message': '邮箱已存在', 'code': 2, 'data': False}
    if reg_data.card_id is not None:  # 验证学号唯一性
        exist_card_id = user_model.get_user_status_by_card_id(reg_data.card_id)
        if exist_card_id is not None:
            return {'message': '学号已存在', 'code': 3, 'data': False}
    return {'message': '满足条件', 'code': 0, 'data': True}


# 获得图片验证码
@users_router.get("/get_captcha")
@user_standard_response
async def get_captcha():
    characters = string.digits + string.ascii_uppercase  # characters为验证码上的字符集，10个数字加26个大写英文字母
    width, height, n_len, n_class = 170, 80, 4, len(characters)  # 图片大小
    generator = ImageCaptcha(width=width, height=height)
    random_str = ''.join([random.choice(characters) for j in range(4)])  # 生出四位随机数字与字母的组合
    img = generator.generate_image(random_str)
    img_byte = BytesIO()
    img.save(img_byte, format='JPEG')  # format: PNG or JPEG
    binary_content = img_byte.getvalue()  # im对象转为二进制流
    captcha = random_str.lower()
    id = captcha_model.add_captcha(captcha)
    img_base64 = base64.b64encode(binary_content).decode('utf-8')
    src = f"data: image/jpeg;base64,{img_base64}"
    return {'data': {'captcha': src, 'captchaId': str(id)}, 'message': '获取成功', 'code': 0}


# 验证图片验证码是否正确并发送邮箱验证码
@users_router.post("/send_captcha")
@user_standard_response
async def send_captcha(captcha_data: captcha_interface, request: Request, user_agent: str = Header(None)):
    value = captcha_model.get_captcha_by_id(int(captcha_data.captchaId))
    if value is None or value[0] != captcha_data.captcha.lower():
        return {'message': '验证码输入错误', 'code': 1, 'data': False}
    captcha_model.delete_captcha(int(captcha_data.captchaId))
    id = None
    str1 = ''
    str2 = ''
    token = str(uuid.uuid4().hex)  # 生成token
    email_token = get_email_token()
    if captcha_data.type == 0:  # 用户首次登陆时发邮件
        user_information = user_model.get_user_email_by_username(captcha_data.username)
        if user_information is None:  # 看看有没有这个用户名
            return {'data': False, 'message': '没有该用户', 'code': 1}
        if user_information[1] != captcha_data.email:  # 看看有没有这个邮箱
            return {'data': False, 'message': '邮箱不正确，不是之前绑定的邮箱', 'code': 2}
        id = user_information[0]
        send_email.delay(captcha_data.email, email_token, 0)  # 异步发送邮件
        str1 = f'用户{id}于xxx首次登陆进行账号激活并向绑定邮箱{user_information[1]}发送验证邮件'
        str2 = '用户激活'
    if captcha_data.type == 1:  # 更改邮箱时发邮件
        id = get_user_id(request)
        old_email = user_model.get_user_by_user_id(int(id))  # 新更改邮箱不能与原邮箱相同
        if old_email.email == captcha_data.email:
            return {'message': '不能与原邮箱相同', 'code': 3, 'data': False}
        send_email.delay(old_email.email, email_token, 1)  # 异步发送邮件
        str1 = f'用户{id}于xxx修改绑定邮箱{old_email.email}并向新邮箱{captcha_data.email}发送验证邮件'
        str2 = '修改邮箱'
    elif captcha_data.type == 2:  # 找回密码时发邮件
        id = user_model.get_user_id_by_email(captcha_data.email)[0]
        str1 = f'用户{id}于xxx找回密码并向绑定邮箱{captcha_data.email}发送邮件'
        str2 = '找回密码'
    parameters = await make_parameters(request)
    add_operation.delay(0, id, str2, str1, parameters, id)
    session = session_interface(user_id=int(id), ip=request.client.host,
                                func_type=1,
                                token=token, user_agent=user_agent, token_s6=email_token,
                                use_limit=1, exp_dt=get_time_now('minutes', 5))  # 新建一个session
    id = session_model.add_session(session)
    if captcha_data.type == 2:
        send_email.delay(captcha_data.email, token, 2)  # 异步发送邮件
    session = session.model_dump()
    user_session = json.dumps(session)
    session_db.set(token, user_session, ex=300)  # 缓存有效session(时效5分钟)
    return {'data': True, 'token_header': token, 'message': '验证码已发送，请前往验证！', 'code': 0}


# 用户通过输入邮箱验证码激活
@users_router.put("/activation")
@user_standard_response
async def user_activation(email_data: email_interface, request: Request, type: int = 0):
    token = request.cookies.get("TOKEN")
    session = session_db.get(token)  # 从缓存中得到有效session
    if session is None:
        session_model.delete_session_by_token(token)
        return {'message': '验证码已过期', 'code': 1, 'data': False}
    user_session = session_model.get_session_by_token(token)  # 根据token获取用户的session
    if user_session is None:
        return {'message': '验证码已过期', 'code': 1, 'data': False}
    if session is not None:  # 在缓存中能找到，说明该session有效
        session = json.loads(session)
        if session['token_s6'] == email_data.token_s6:  # 输入的验证码正确
            session_model.update_session_use(user_session.id, 1)  # 把这个session使用次数设为1
            session_model.delete_session(user_session.id)  # 把这个session设为无效
            session_db.delete(token)
            parameters = await make_parameters(request)
            if type == 0:  # 用户激活时进行验证
                user_model.update_user_status(user_session.user_id, 0)
                add_operation.delay(0, user_session.user_id, '用户激活',
                                    f'用户{user_session.user_id}于xxx进行用户激活时输入邮箱验证码{email_data.token_s6}通过邮箱验证',
                                    parameters,
                                    user_session.user_id)
                return {'message': '验证成功', 'data': True, 'token_header': '-1', 'code': 0}
            if type == 1:  # 修改邮箱时进行验证
                user_model.update_user_email(user_session.user_id, email_data.email)
                add_operation.delay(0, user_session.user_id, '修改邮箱',
                                    f'用户{user_session.user_id}于xxx修改邮箱时输入邮箱验证码{email_data.token_s6}通过邮箱验证',
                                    parameters,
                                    user_session.user_id)
                return {'message': '验证成功', 'data': True, 'token_header': '-1', 'code': 0}
        else:
            return {'message': '验证码输入错误', 'code': 2, 'data': False}
    else:  # 缓存中找不到，说明已无效
        session_model.delete_session(user_session.id)
        return {'message': '验证码已过期', 'code': 1, 'data': False}


# 输入账号密码进行登录
@users_router.post("/login")
@user_standard_response
async def user_login(log_data: login_interface, request: Request, user_agent: str = Header(None),
                     token=Depends(auth_not_login)):
    user_information = user_model.get_user_by_username(log_data.username)  # 先查看要登录的用户名是否存在
    if user_information is None:  # 用户名不存在
        return {'message': '用户名或密码不正确', 'data': False, 'code': 1}
    else:  # 用户名存在
        new_password = log_data.password
        if new_password == user_information.password:
            status = user_model.get_user_status_by_username(log_data.username)[0]  # 登陆时检查帐号状态
            if status == 1:
                return {'message': '账号未激活', 'data': {"first_time": True}, 'code': 0}
            elif status == 2:
                return {'message': '账号已注销', 'data': False, 'code': 3}
            elif status == 3:
                return {'message': '账号被封禁', 'data': False, 'code': 4}
            token = str(uuid.uuid4().hex)
            session = session_interface(user_id=int(user_information.id), ip=request.client.host,
                                        func_type=0,
                                        token=token, user_agent=user_agent, exp_dt=
                                        get_time_now('days', 14))
            id = session_model.add_session(session)
            session = session.model_dump()
            user_session = json.dumps(session)
            session_db.set(token, user_session, ex=1209600)  # 缓存有效session
            parameters = await make_parameters(request)
            add_operation.delay(0, int(user_information.id), '用户登录',
                                f'用户{user_information.id}于xxx输入账号，密码登录', parameters,
                                int(user_information.id))
            return {'message': '登陆成功', 'token': token, 'data': {"first_time": False}, 'code': 0}
        else:
            return {'message': '用户名或密码不正确', 'data': False, 'code': 1}


# 下线
@users_router.put("/logout")
@user_standard_response
async def user_logout(request: Request, session=Depends(auth_login)):
    token = session['token']
    mes = session_model.delete_session_by_token(token)  # 将session标记为已失效
    session_db.delete(token)  # 在缓存中删除
    parameters = await make_parameters(request)
    add_operation.delay(0, session['user_id'], '用户登出', f"用户{session['user_id']}于xxx登出", parameters,
                        session['user_id'])
    return {'message': '下线成功', 'data': {'result': mes}, 'token': '-1', 'code': 0}


# 输入原密码与新密码更改密码
@users_router.put("/password_update")
@user_standard_response
async def user_password_update(request: Request, password: password_interface, session=Depends(auth_login)):
    user_id = session['user_id']
    user = user_model.get_user_by_user_id(user_id)
    if user.password != password.old_password:  # 原密码输入错误
        return {'message': '密码输入不正确', 'data': False, 'code': 1}
    if user.password == password.new_password:  # 新密码与旧密码相同
        return {'message': '新密码不能与旧密码相同', 'data': False, 'code': 2}
    id = user_model.update_user_password(user_id, password.new_password)  # 更新新密码
    parameters = await make_parameters(request)
    add_operation.delay(0, id, '修改密码', f"用户{session['user_id']}于xxx修改密码", parameters, id)
    return {'data': {'user_id': id}, 'message': '修改成功', 'code': 0}


# 输入验证码确认正确后，输入更改邮箱对邮箱进行更改
@users_router.post("/email_update")
@user_standard_response
async def user_email_update(email_data: email_interface, request: Request, session=Depends(auth_login)):
    result = await user_activation(email_data, request, 1)  # 验证验证码是否输入正确
    ans = json.loads(result.body)
    user_information = user_information_db.get(session["user_id"])
    if user_information is not None:
        user_information = json.loads(user_information)
        user_information['email'] = email_data.email
        user_information_db.set(session["user_id"], json.dumps(user_information), ex=1209600)  # 缓存有效session
    else:
        session_model.delete_session_by_token(session["token"])
    return {'data': True, 'message': ans['message'], 'code': 0}


# 输入用户名，邮箱找回密码
@users_router.post("/get_back_password")
@user_standard_response
async def user_password_get_back(captcha_data: captcha_interface, request: Request, user_agent: str = Header(None)):
    user_information = user_model.get_user_by_username(captcha_data.username)
    if user_information is None:  # 看看有没有这个用户名
        return {'data': False, 'message': '没有该用户', 'code': 1}
    if user_information.email != captcha_data.email:  # 看看有没有这个邮箱
        return {'data': False, 'message': '邮箱不正确，不是之前绑定的邮箱', 'code': 2}
    captcha_data.type = 2
    result = await send_captcha(captcha_data, request, user_agent)
    ans = json.loads(result.body)
    return {'data': True, 'message': ans['message'], 'code': 0}


# 找回密码后用户输入新密码设置密码
@users_router.get("/set_password/{token}")
@user_standard_response
async def user_set_password(request: Request, new_password: str, token: str):
    user_id = session_model.get_user_id_by_token(token)  # 查出user_id
    if user_id is None:
        return {'data': False, 'message': '无法找到该页面', 'code': 1}
    user_id = user_id[0]
    user_information = user_model.get_user_by_user_id(user_id)
    if user_information.password == new_password:
        return {'data': False, 'message': '新密码不能与原密码相同', 'code': 2}
    user_model.update_user_password(user_id, new_password)  # 设置密码
    parameters = await make_parameters(request)
    add_operation.delay(0, user_id, '忘记密码', f'用户{user_information.username}输入新密码重设密码',
                        parameters, user_id)
    return {'data': True, 'message': '修改成功', 'code': 0}


# 查看用户信息
@users_router.get("/getProfile")
@user_standard_response
async def user_get_Profile(request: Request, session=Depends(auth_login)):
    data = get_user_information(session['user_id'])
    parameters = await make_parameters(request)
    add_operation.delay(0, None, '查看用户信息', f"用户{session['user_id']}于xxx查看个人信息", parameters,
                        session['user_id'])
    return {'data': data, 'message': '结果如下', 'code': 0}


@users_router.get("/error")  # 检查用户异常状态原因
@user_standard_response
async def user_get_error(username: str, password: str, email: str):
    exist_user = user_model.get_user_some_by_username(username)
    if exist_user is None:
        return {'message': '没有该用户', 'data': False, 'code': 1}
    if exist_user[0] != email:
        return {'message': '用户绑定邮箱不正确', 'data': False, 'code': 2}
    if exist_user[1] != password:
        return {'message': '密码不正确', 'data': False, 'code': 3}
    reasons = operation_model.get_operation_by_service_type(0, exist_user[3], '封禁用户')  # 查看被封禁原因
    reason = extract_word_between(reasons[0], '因为', '而')[0]
    oper_user_id = reasons[1]
    username = user_model.get_user_name_by_user_id(oper_user_id)[0]  # 看被谁封禁
    return {'message': '用户异常状态原因', 'data': {'封禁原因': reason, '封禁人': username}, 'code': 0}


@users_router.get("/verify_hash")  # 验证区块链传的hash是否正确并返回给前端
@user_standard_response
async def user_verify_hash(request: Request, permission=Depends(auth_login)):
    id_list = request.query_params.getlist('id_list[]')
    hashs = operation_model.get_operation_hash_by_id_list(id_list)
    headers = block_chains_login()
    results = []
    for hash in hashs:
        bashash = block_chains_get(hash[1], headers)
        if bashash is not None:
            results.append(
                {'id': hash[0], 'verify': True, 'block_number': bashash['block_number'], 'blockchain_hash': hash[1]})
        else:
            results.append({'id': hash[0], 'verify': False})
    parameters = await make_parameters(request)
    add_operation.delay(1, None, '操作验证', f"用户{permission['user_id']}于xxx验证操作是否上链",
                        parameters,
                        permission['user_id'])
    return {'message': '验证结果如下', 'data': results, 'code': 0}


@users_router.get("/get_operation")  # 获取用户的所有操作
@page_response
async def user_get_operation(pageNow: int, pageSize: int, request: Request, service_type: int = None,
                             service_id: int = None,
                             permission=Depends(auth_login)):
    Page = page(pageSize=pageSize, pageNow=pageNow)
    if service_type is None:
        all_operations, counts = operation_model.get_func_and_time_by_admin(Page, permission['user_id'])
    else:
        all_operations, counts = operation_model.get_operation_by_service(Page, permission['user_id'], service_type,
                                                                          service_id)
    result = {'rows': None}
    if all_operations:
        operation_data = []
        for operation in all_operations:  # 对每个操作的数据进行处理
            dict = {'func': operation[0], 'oper_dt': operation[1].strftime(
                "%Y-%m-%d %H:%M:%S"), 'id': operation[2], 'local_hash': operation[3]}
            operation_data.append(dict)
        result = makePageResult(Page, counts, operation_data)
    parameters = await make_parameters(request)
    if service_type is None:
        str = f"用户{permission['user_id']}于xxx获取用户{permission['user_id']}所有操作"
    if service_type == 5:
        str = f"用户{permission['user_id']}于xxx获取用户{permission['user_id']}对资源{service_id}所有操作"
    elif service_type == 6:
        str = f"用户{permission['user_id']}于xxx获取用户{permission['user_id']}对资金{service_id}所有操作"
    elif service_type == 7:
        str = f"用户{permission['user_id']}于xxx获取用户{permission['user_id']}对项目{service_id}所有操作"
    add_operation.delay(service_type, service_id, '获取用户操作', str,
                        parameters,
                        permission['user_id'])
    return {'message': '操作如下', "data": result, "code": 0}


@users_router.get("/block_chain_information")  # 获取区块链信息
@user_standard_response
async def get_block_chain_information(request: Request, permission=Depends(auth_login), oj_headers=Depends(oj_login)):
    headers = block_chains_login()
    result = await block_chains_information(headers, oj_headers)
    parameters = await make_parameters(request)
    add_operation.delay(1, None, '获取区块链信息', f"用户{permission['user_id']}于xxx获取区块链信息", parameters,
                        permission['user_id'])
    return {'message': '区块链信息结果如下', 'data': result, 'code': 0}


@users_router.get("/get_user_information")  # 查询某子用户的所有信息
@page_response
async def user_get_all_user_information(request: Request, pageNow: int, pageSize: int, username: str = None,
                                        school: str = None, session=Depends(auth_login)):
    result = {'rows': None}
    Page = page(pageNow=pageNow, pageSize=pageSize)
    tn, res = user_model.get_user_information_by_name_school(username, school, Page)
    if res:
        result = makePageResult(Page, tn, res)
    parameters = await make_parameters(request)
    add_operation.delay(1, session['user_id'], '查询用户信息', f"用户{session['user_id']}于xxx查询子用户个人信息",
                        parameters,
                        session['user_id'])
    return {'message': '操作如下', "data": result, "code": 0}


@users_router.post("/oj_bind")  # 绑定oj账号
@user_standard_response
async def oj_bind(request: Request, bind_data: oj_login_interface, session=Depends(oj_not_login)):
    oj_bind_func(bind_data.oj_username, bind_data.oj_password, session['user_id'])
    user_info_model.update_user_oj(session['user_id'], bind_data.oj_username, bind_data.oj_password)
    parameters = await make_parameters(request)
    add_operation.delay(1, session['user_id'], '绑定oj账号', f"{session['user_id']}于xxx绑定oj账号", parameters,
                        session['user_id'])
    return {'message': '绑定成功', 'data': True, 'code': 0}


@users_router.put("/oj_unbind")  # 解绑oj账号
@user_standard_response
async def oj_unbind(request: Request, oj=Depends(oj_login),session = Depends(auth_login)):
    user_info_model.delete_user_oj(session['user_id'])
    parameters = await make_parameters(request)
    user_information = user_information_db.get(session["user_id"])
    user_information = json.loads(user_information)
    user_information['oj_username'] = None
    user_information['oj_bind'] = 0
    user_information_db.set(session["user_id"], json.dumps(user_information), ex=1209600)  # 缓存有效session
    add_operation.delay(1, session['user_id'], '解绑oj账号', f"{session['user_id']}于xxx解绑oj账号", parameters,
                        session['user_id'])
    return {'message': '解绑成功', 'data': True, 'code': 0}

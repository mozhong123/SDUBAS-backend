import json

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.encoders import jsonable_encoder

import type.permissions
from service.permissions import permissionModel
from type.functions import get_user_id
from type.page import page
from utils.response import standard_response
from utils.response import makePageResult
from utils.auth_permission import *

permissions_router = APIRouter()


@permissions_router.post("/select_son_user")
async def add(data: type.permissions.create_role_base):
    db = permissionModel()
    obj_dict = jsonable_encoder(data)
    return {"new_role": db.get_role_info_by_id(db.create_role(obj_dict['role_name'], obj_dict['role_superiorId']))}


@permissions_router.post("/add")  # 创建角色
async def add_role(data: type.permissions.create_role_base):
    db = permissionModel()
    obj_dict = jsonable_encoder(data)
    return {'message': '状态如下',
            "new_role": db.get_role_info_by_id(db.create_role(obj_dict['role_name'], obj_dict['role_superiorId']))}


@permissions_router.post("/delete")  # 删除角色(取消)
@standard_response
async def delete_role(data: type.permissions.delete_role_base):
    db = permissionModel()
    return {'message': '状态如下', "data": db.delete_role(data)}


@permissions_router.post("/attribute_role_for_user")  # 分配用户角色
async def attribute_role(data: type.permissions.attribute_role_base):
    db = permissionModel()
    return db.attribute_user_role(data.user_id, data.role_id)

@permissions_router.post("/attribute_privilege")  # 为角色添加权限
@standard_response
async def attribute_privilege_for_role(data: type.permissions.attribute_privilege_base):
    db = permissionModel()
    return {'message': '状态如下', "status": db.attribute_privilege_for_role(data.privilege_list, data.role_id)}




@permissions_router.post("/add_role_for_work")  # 为业务添加角色
@standard_response
async def add_role_for_work(request: Request, data: type.permissions.Add_Role_For_Work_Base):
    db = permissionModel()
    obj_dict = jsonable_encoder(data)
    user_id = get_user_id(request)
    superiorId = db.search_user_default_role(user_id)
    role_id = db.create_role(obj_dict['role_name'], superiorId)
    WorkRole_id = db.attribute_role_for_work(obj_dict['service_type'], obj_dict['service_id'], role_id)
    return WorkRole_id


@permissions_router.post("/test")
@standard_response
async def test(request: Request):
    db = permissionModel()
    return db.create_work_role(1, 'xueyuan', 2)


@permissions_router.post("/auth_privilege")  # 权限验证
@standard_response
async def auth_privilege(request: Request):
    db = permissionModel()
    user_id = int(request.headers.get("user_id"))
    permission_key = request.url.path
    permission = None
    role_list = db.search_role_by_user(user_id)
    privilege_set = db.search_privilege_by_role(role_list)
    json_string = json.dumps(list(privilege_set))
    permission = db.check_permission(permission_key, privilege_set)
    if not permission:
        raise HTTPException(
            status_code=403,
            detail="No permission",
        )
    return {"privilege": json_string}


@permissions_router.post("/work_id")  # 返回业务id
@standard_response
async def return_work_id(request: Request):
    db = permissionModel()
    user_id = int(request.headers.get("user_id"))
    role_list = db.search_role_by_user(user_id)
    work_list = db.search_work_by_role(role_list)
    json_string = json.dumps(work_list)
    return {"work_id": json_string}


@permissions_router.post("/search_service_id")  # 返回业务id(不可用)
@standard_response
async def return_service_id(request: Request, data: type.permissions.Return_Service_Id):
    db = permissionModel()
    user_id = int(request.headers.get("user_id"))
    permission_key = request.url.path
    permission = None
    role_list = db.search_role_by_user(user_id)
    service_id = db.search_service_id(role_list, data.service_type, data.name)
    return {"service_id": service_id}


@permissions_router.post("/search_user_id")  # 返回用户id
@standard_response
async def return_user_id(request: Request, data: type.permissions.Return_User_Id):
    db = permissionModel()
    count = db.search_user_id_by_service(data.service_type, data.service_id)
    return count


@permissions_router.post("/default_role_id")  # 返回学院默认角色id
@standard_response
async def default_role_id(request: Request):
    db = permissionModel()
    user_id = int(request.headers.get("user_id"))
    permission_key = request.url.path
    permission = None
    role_list = db.search_role_by_user(user_id)
    role_id = db.search_college_default_role_id(role_list)
    return {"role_id": role_id}


@permissions_router.get("/return_privilege_list")  # 返回权限列表(使用)
@standard_response
async def return_privilege_list(request: Request, service_type: int = Query()):
    db = permissionModel()
    privilege_list = db.search_privilege_list(service_type)
    return privilege_list


@permissions_router.post("/add_default_role")  # 创建默认角色(使用)
@standard_response
async def add_role(request: Request, data: type.permissions.create_default_role_Base):
    db = permissionModel()
    res = data.roles
    superiorId = db.search_user_default_role(user['user_id'])
    for item in res:
        role_id = db.create_role(item.role_name, superiorId)
        db.add_default_work_role(user['user_id'], role_id)
        db.attribute_privilege_for_role(item.privilege_list, role_id)
    return 'OK'


# @permissions_router.post("/add_default_work_role")  # 业务角色表里添加默认角色
# @standard_response
# async def add_work_role(request: Request, data: type.permissions.create_default_work_role_base, user=Depends(auth_login)):
#     db = permissionModel()
#     obj_dict = jsonable_encoder(data)
#     user_id = user['user_id']
#     return db.add_default_work_role(user_id, obj_dict['role_id'])


@permissions_router.get("/get_user_info")  # 查找角色所有用户(使用)
@standard_response
async def get_user_info(role_id: int = Query(),
                        pageNow: int = Query(description="页码", gt=0),
                        pageSize: int = Query(description="每页数量", gt=0), user=Depends(auth_login)):
    user_id = user['user_id']
    # user_id = int(request.headers.get("user_id"))
    db = permissionModel()
    Page = page(pageNow=pageNow, pageSize=pageSize)
    tn, res = db.get_user_info_by_role(role_id=role_id)
    return makePageResult(pg=Page, tn=tn, data=res)


@permissions_router.get("/search_created_role")  # 查找创建的角色(使用)
@standard_response
async def search_created_role(request: Request, pageNow: int = Query(description="页码", gt=0),
                        pageSize: int = Query(description="每页数量", gt=0), user=Depends(auth_login)):
    db = permissionModel()
    user_id = user['user_id']
    Page = page(pageNow=pageNow, pageSize=pageSize)
    tn, res = db.search_role_by_user_2(user_id=user_id, pg=Page)
    return makePageResult(pg=Page, tn=tn, data=res)


@permissions_router.get("/get_work_role")  # 请求项目角色(使用)
@standard_response
async def get_work_role(request: Request, service_id: int = Query(), service_type: int = Query(),
                        pageNow: int = Query(description="页码", gt=0),
                        pageSize: int = Query(description="每页数量", gt=0), user=Depends(auth_login)):
    db = permissionModel()
    # user_id = int(request.headers.get("user_id"))
    Page = page(pageNow=pageNow, pageSize=pageSize)
    tn, res = db.get_role_by_work(service_type, service_id)
    return makePageResult(pg=Page, tn=tn, data=res)


@permissions_router.get("/search_created_user")  # 查找创建的用户
@standard_response
async def search_created_user(request: Request, pageNow: int = Query(description="页码", gt=0),
                        pageSize: int = Query(description="每页数量", gt=0), user=Depends(auth_login)):
    db = permissionModel()
    user_id = user['user_id']
    Page = page(pageNow=pageNow, pageSize=pageSize)
    tn, res = db.search_created_user_info(user_id=user_id)
    return makePageResult(pg=Page, tn=tn, data=res)

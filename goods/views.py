from user.auth import CheckUserWrap
from user.tools import wxapp_redis, is_action_allowed

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import DetailView, FormView, ListView, View
from dss.Mixin import (FormJsonResponseMixin, JsonResponseMixin,
                       MultipleJsonResponseMixin)
from dss.Serializer import serializer

from .models import *


class GoodsListView(MultipleJsonResponseMixin, ListView):
    model = Goods
    paginate_by = 15
    foreign = True
    datetime_format = 'string'

    def get_queryset(self):
        kwargs = {
        }

        category = self.request.GET.get('category', None)
        pintuan = True if int(self.request.GET.get('pintuan') or 0) else False
        search = self.request.GET.get('search', None)
        ordering = self.request.GET.get('order', None)  # view, sale, love
        ordertype = int(self.request.GET.get('ordertype')
                        or 0)  # 0  desc 1 or other asc

        if category:
            kwargs['category_id'] = category
        if pintuan:
            kwargs['pintuangoods__begin_time__lte'] = timezone.now()
            kwargs['pintuangoods__end_time__gte'] = timezone.now()
        if search:
            kwargs['name__contains'] = search
        if ordering == 'pintuan_price':
            kwargs['pintuangoods__pintuan_price__isnull'] = False

        queryset = super(GoodsListView, self).get_queryset().filter(
            goods_status=1, **kwargs)
        ordering = self.get_order_param(ordering)
        if ordering:
            ordering = ordering if ordertype else '-' + ordering
            queryset = queryset.order_by(ordering)
        return queryset

    def get_order_param(self, ordering):
        if ordering in ['view', 'sale', 'love']:
            return 'goodsprofile__{}_count'.format(ordering)
        elif ordering in ['create_time', 'now_price']:
            return ordering
        elif ordering in ['pintuan_price']:
            return 'pintuangoods__{}'.format(ordering)

        return None

    def get_context_data(self, **kwargs):
        goods_list = []
        context = super(GoodsListView, self).get_context_data(**kwargs)
        _goods_list = context.pop('goods_list')
        for i in _goods_list:
            info = serializer(i, exclude_attr=('category_id',),
                              datetime_format=self.datetime_format)
            info['count'] = {
                'view_count': int(wxapp_redis.zscore("wxapp:goodsview:view_count", i.id) or 0),
                'sale_count': i.goodsprofile.sale_count,
                'love_count': wxapp_redis.hlen("wxapp:goodslove:{}".format(i.id)),
            }
            info['is_pintuan'] = i.is_pintuan()
            if info['is_pintuan']:
                info['pintuan_info'] = serializer(i.pintuangoods, exclude_attr=('goods', 'goods_id'),
                                                  datetime_format=self.datetime_format)
                info['pintuan_info']['participate_count'] = i.simpleorderdetail_set.filter(
                    order__order_type=1).count()
            else:
                info['pintuan_info'] = {}
            goods_list.append(info)
        context['goods_list'] = goods_list
        return context


class GoodsDetailView(JsonResponseMixin, DetailView, CheckUserWrap):
    model = GoodsDetail
    foreign = True

    many = True
    datetime_type = 'string'
    pk_url_kwarg = 'goods_id'
    # exclude_attr = ('id',)
    datetime_format = 'string'

    def get_context_data(self, **kwargs):
        context = super(GoodsDetailView, self).get_context_data(**kwargs)
        context['count'] = {
            'view_count': int(wxapp_redis.zscore("wxapp:goodsview:view_count", self.object.pk) or 0),
            'sale_count': self.object.goods.goodsprofile.sale_count,
            'love_count': wxapp_redis.hlen("wxapp:goodslove:{}".format(self.object.pk)),
            # 'sale_count': self.object.goods.goodsprofile.sale_count,
            # 'view_count': self.object.goods.goodsprofile.view_count,
            # 'love_count': self.object.goods.goodsprofile.love_count
        }
        context['is_pintuan'] = self.object.goods.is_pintuan()
        context['pintuan_info'] = serializer(self.object.goods.pintuangoods, exclude_attr=('goods', 'goods_id'),
                                             datetime_format=self.datetime_format) if context['is_pintuan'] else {}
        self.update_view()
        return context

    def update_view(self):
        """
        redis 更新浏览量， 定时任务数据落地
        每个用户 每天浏览多次只记录一次，
        用户鉴权不通过的不计入
        """
        if self.wrap_check_token_result():
            user_key = ':'.join(['wxapp', 'goodsview', 'user', str(
                self.user.openid), str(self.object.goods.id)])
            view_key = ':'.join(['wxapp', 'goodsview', 'view_count'])
            if not wxapp_redis.exists(user_key):
                wxapp_redis.zincrby(view_key, self.object.goods.id)
                wxapp_redis.set(user_key, 1, ex=25 * 3600)


class LoveGoodsView(JsonResponseMixin, View, CheckUserWrap):
    model = Goods
    pk_url_kwarg = 'goods_id'

    def get(self, request, *args, **kwargs):
        self.get_object()
        info = {}
        key = ':'.join(['wxapp', 'goodslove', str(self.obj.id)])
        if not self.wrap_check_token_result():
            return self.render_to_response({'msg': self.msg})

        love_users = []
        if wxapp_redis.exists(key):
            user_keys = wxapp_redis.hkeys(key)
            for i in user_keys:
                love_users.append(
                    eval(wxapp_redis.hget(key, i.decode("utf-8"))))

        info['love_users'] = love_users
        info['is_love'] = wxapp_redis.hexists(key, self.user.openid)

        return self.render_to_response(info)

    def post(self, request, *args, **kwargs):
        self.get_object()
        if not self.wrap_check_token_result():
            return self.render_to_response({'msg': self.msg})

        # 限流策略
        # 1 普通动态时间窗口限流，2 使用redis-cell 漏洞限流算法
        # 第二种windows 不支持模块 先用第一种吧
        # 第二种：
        # a, b, c, d, e = wxapp_redis.execute_command("cl.throttle","userlove_{}".format(user.id), 15, 10, 60)
        # if a:
        #     return self.render_to_response({'msg': '你的操作太频繁了，请在{}秒后重试'.format(d)})
        if not is_action_allowed(self.user.id, "userlove", 60, 30):
            return self.render_to_response({'msg': '你的操作太频繁了，请在稍后重试'})

        key = ':'.join(['wxapp', 'goodslove', str(self.obj.id)])
        if not wxapp_redis.hexists(key, self.user.openid):
            wxapp_redis.hset(key, self.user.openid, serializer(
                self.user, exclude_attr=('reg_date', 'last_login', 'openid')))
        else:
            wxapp_redis.hdel(key, self.user.openid)

        return self.get(request, *args, **kwargs)

    def get_object(self):
        pk = self.kwargs.get(self.pk_url_kwarg)

        queryset = self.model._default_manager.all()
        queryset = queryset.filter(pk=pk)

        try:
            self.obj = queryset.get()
        except queryset.model.DoesNotExist:
            raise Http404(_("No %(verbose_name)s found matching the query") %
                          {'verbose_name': queryset.model._meta.verbose_name})
        return self.obj


def all_category_view(request):
    all_cate = CateGory.objects.all()
    return JsonResponse({'lists': serializer(all_cate)})

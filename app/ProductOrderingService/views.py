from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.views import APIView
from rest_framework import status, mixins

from django.http import JsonResponse, Http404
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.forms import model_to_dict
from django.shortcuts import render
from yaml import load as load_yaml, Loader

from ProductOrderingService import models
from ProductOrderingService import serializers
from ProductOrderingService.permissions import IsOwner

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse, OpenApiExample

RESPONS_DICT = {status.HTTP_200_OK: serializers.CategorySerializer,
                status.HTTP_400_BAD_REQUEST: serializers.DummyDetailSerializer,
                status.HTTP_401_UNAUTHORIZED: serializers.DummyDetailSerializer,
                status.HTTP_403_FORBIDDEN: serializers.DummyDetailAndStatusSerializer,
                status.HTTP_500_INTERNAL_SERVER_ERROR: OpenApiResponse(
                    response=None,
                    description='Описание 500 ответа'),
                }


@extend_schema(tags=["Upload Products"])
class UploadViewSet(APIView):
    """Класс для загрузки информации о товарах в БД интернет-магазина"""

    @extend_schema(description='Загрузка списка продуктов из файла',
                   summary='Загрузка списка продуктов из файла',
                   )
    def post(self, request, *args, **kwargs):
        """
        Метод для загрузки каталога товаров по каждому магазину.

        Принимает yaml-файл в качестве аргумента.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)

        file = request.data.get("File")
        if file:
            validate_file = FileExtensionValidator(['yaml'])
            try:
                validate_file(file)
            except ValidationError as e:
                return JsonResponse({'Status': False, 'Error': str(e)})
            else:
                data = load_yaml(file, Loader=Loader)
                shop, _ = models.Shop.objects.get_or_create(name=data['shop'], user_id=request.user.id)

                for category in data['categories']:
                    category_object, _ = models.Category.objects.get_or_create(id=category['id'], name=category['name'])
                    category_object.shops.add(shop.id)
                    category_object.save()
                models.ProductInfo.objects.filter(shop_id=shop.id).delete()
                for item in data['goods']:
                    product, _ = models.Product.objects.get_or_create(name=item['name'], category_id=item['category'])
                    product_info = models.ProductInfo.objects.create(product_id=product.id,
                                                                     external_id=item['id'],
                                                                     model=item['model'],
                                                                     price=item['price'],
                                                                     price_rrc=item['price_rrc'],
                                                                     quantity=item['quantity'],
                                                                     shop_id=shop.id)
                    for name, value in item['parameters'].items():
                        parameter_object, _ = models.Parameter.objects.get_or_create(name=name)
                        models.ProductParameter.objects.create(product_info_id=product_info.id,
                                                               parameter_id=parameter_object.id,
                                                               value=value)
                return JsonResponse({'Status': True})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


@extend_schema(tags=["Shop"])
@extend_schema_view(
    list=extend_schema(description='Получение всех магазинов',
                       summary='Получение всех категорий',
                       responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ShopSerializer}
                       ),
    retrieve=extend_schema(description='Получение одного магазина',
                           summary='Получение одного категории',
                           responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ShopSerializer}
                           ),
)
class ShopViewSet(GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    """Класс для просмотра списка интернет-магазина"""
    queryset = models.Shop.objects.all()
    serializer_class = serializers.ShopSerializer


@extend_schema(tags=["Category"])
@extend_schema_view(
    list=extend_schema(description='Получение всех категорий',
                       summary='Получение всех категорий',
                       responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.CategorySerializer}
                       ),
    retrieve=extend_schema(description='Получение одного категории',
                           summary='Получение одного категории',
                           responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.CategorySerializer}
                           ),
)
class CategoriesViewSet(GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    """Класс для просмотра списка категорий"""
    queryset = models.Category.objects.all()
    serializer_class = serializers.CategorySerializer


@extend_schema(tags=["Product"])
@extend_schema_view(
    list=extend_schema(description='Получение всех продуктов',
                       summary='Получение всех продуктов',
                       responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ProductSerializer}
                       ),
    retrieve=extend_schema(description='Получение одного продукта',
                           summary='Получение одного продукта',
                           responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ProductSerializer}
                           ),
)
class ProductViewSet(GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    """Класс для просмотра продуктов интернет-магазина"""
    queryset = models.Product.objects.all()
    serializer_class = serializers.ProductSerializer


@extend_schema(tags=["Basket List"])
class BasketView(APIView):
    """Класс для работы со списком заказов"""

    @extend_schema(description='Просмотр списка заказов',
                   summary='Просмотр списка заказов',
                   responses=RESPONS_DICT,
                   )
    def get(self, request, *args, **kwargs):
        """Метод для просмотра списка заказов"""
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        basket = models.Order.objects.filter(
            user_id=request.user.id, state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').distinct()
        serializer = serializers.OrderSerializer(basket, many=True)
        return Response(serializer.data)

    @extend_schema(description='Создание заказа',
                   summary='Создание заказа',
                   responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.OrderSerializer},
                   )
    def post(self, request, *args, **kwargs):
        """Метод для создания заказа"""
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        items_dict = request.data.get('ordered_items')
        if items_dict:
            basket = models.Order.objects.create(user_id=request.user.id, state='basket')
            for order_item in items_dict:
                order_item.update({'order': basket.id})
                serializer = serializers.OrderItemSerializer(data=order_item)
                if serializer.is_valid():
                    serializer.save()
                else:
                    return JsonResponse({'Status': False, 'Errors': serializer.errors})
            return JsonResponse({'Status': True, 'Создано объектов': model_to_dict(basket)})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


@extend_schema(tags=["Basket"])
class BasketViewDetail(APIView):
    """Класс для работы с карточкой заказа"""

    @extend_schema(description='Просмотр одного заказа',
                   summary='Просмотр одного заказа',
                   responses=RESPONS_DICT,
                   )
    def get(self, request, *args, **kwargs):
        """Метод для просмотра карточки заказов."""
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        pk = kwargs.get('pk', None)
        if not pk:
            return JsonResponse({'Error': 'Method DELETE not allowed'}, status=403)
        else:
            basket = models.Order.objects.filter(
                user_id=request.user.id, state='basket', id=pk).prefetch_related(
                'ordered_items__product_info__product__category',
                'ordered_items__product_info__product_parameters__parameter').distinct()
            serializer = serializers.OrderSerializer(basket, many=True)
            return Response(serializer.data)

    @extend_schema(description='Обновление одного заказа',
                   summary='Обновление одного заказа',
                   responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.OrderSerializer},
                   )
    def put(self, request, *args, **kwargs):
        """Метод для обновления или добавления продуктов к заказу."""
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        pk = kwargs.get('pk', None)
        if not pk:
            return JsonResponse({'Error': 'Method PUT not allowed'}, status=403)

        items_dict = request.data.get('ordered_items')
        if items_dict:
            for order_item in items_dict:
                if order_item.get('id') is None:
                    order_item.update(order=pk)
                    serializer = serializers.OrderItemSerializer(data=order_item)
                    if serializer.is_valid():
                        serializer.save()
                    else:
                        return JsonResponse({'Status': False, 'Errors': serializer.errors})
                else:
                    items = models.OrderItem.objects.filter(id=order_item['id']).update(
                        quantity=order_item['quantity'],
                        product_info=order_item["product_info"]
                    )
            return JsonResponse({'Status': True})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    @extend_schema(description='Удаление заказа',
                   summary='Удаление заказа',
                   responses=RESPONS_DICT,
                   )
    def delete(self, request, *args, **kwargs):
        """Метод для удаления заказа."""
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        pk = kwargs.get('pk', None)
        if not pk:
            return JsonResponse({'Error': 'Method DELETE not allowed'}, status=403)

        order = models.Order.objects.filter(user_id=request.user.id, id=pk)
        if order.first() is None:
            return JsonResponse({'Error': 'Method DELETE  is not applicable to the specified object'}, status=403)
        else:
            order.delete()
            return JsonResponse({'Status': True, 'Answer': 'Order delete'}, status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Orders Shop"])
class PartnerOrders(APIView):
    """Класс для получения заказов поставщиками"""

    @extend_schema(description='Просмотр заказов каждого магазина',
                   summary='Просмотр заказов каждого магазина',
                   responses=RESPONS_DICT,
                   )
    def get(self, request, *args, **kwargs):
        """Метод для получения списка заказов магазина"""

        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)

        order = models.Order.objects.filter(
            ordered_items__product_info__shop__user_id=request.user.id).exclude(state='basket'). \
            prefetch_related('ordered_items__product_info__product__category',
                             'ordered_items__product_info__product_parameters__parameter'). \
            select_related('contact').distinct()
        serializer = serializers.OrderSerializer(order, many=True)
        return Response(serializer.data)


@extend_schema(tags=["Orders"])
@extend_schema_view(
    list=extend_schema(description='Получение всех заказов',
                       summary='Получение всех заказов',
                       responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.OrderSerializer}
                       ),
    retrieve=extend_schema(description='Получение одного заказа',
                           summary='Получение одного заказа',
                           responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.OrderSerializer}
                           ),
    update=extend_schema(description='Привязка контакта и адреса доставки',
                         summary='Привязка контакта и адреса доставки',
                         responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.OrderSerializer}
                         ),
)
class OrderViewSet(mixins.RetrieveModelMixin,
                   mixins.UpdateModelMixin,
                   mixins.ListModelMixin,
                   GenericViewSet):
    """Класс для просмотра и работы с заказами"""
    queryset = models.Order.objects.all()
    serializer_class = serializers.OrderSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Метод выводит заказы конкретного пользователя исходя из переданного токена"""
        queryset = self.queryset
        query_set = queryset.filter(user=self.request.user)
        return query_set

    def perform_create(self, serializer):
        """Метод позволяет автоматически заполнить поля user при создании заказа исходя из переданного токена"""
        serializer.save(user=self.request.user)

    def partial_update(self, request, pk=None):
        serializer = serializers.OrderSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@extend_schema(tags=["Contact"])
@extend_schema_view(
    list=extend_schema(description='Получение всех контактов',
                       summary='Получение всех контактов',
                       responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ContactSerializer}
                       ),
    retrieve=extend_schema(description='Получение одного контакта',
                           summary='Получение одного контакта',
                           responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ContactSerializer}
                           ),
    update=extend_schema(description='Обновление контакта',
                         summary='Обновление контакта с помощью PUT',
                         responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ContactSerializer}
                         ),
    destroy=extend_schema(description='Удаление контакта',
                          summary='Удаление контакта',
                          responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ContactSerializer}
                          ),
    create=extend_schema(description='Создание контакта',
                         summary='Создание контакта',
                         responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ContactSerializer}
                         ),
    partial_update=extend_schema(description='Обновление контакта',
                                 summary='Создание  помощью PATCH',
                                 responses=RESPONS_DICT | {status.HTTP_200_OK: serializers.ContactSerializer}
                                 ),
)
class ContactViewSet(ModelViewSet):
    """Класс для работы с указанным контактом"""

    queryset = models.Contact.objects.all()
    serializer_class = serializers.ContactSerializer
    permission_classes = [IsOwner]

    def get_queryset(self):
        """Метод выводит заказы конкретного пользователя исходя из переданного токена"""
        queryset = self.queryset
        query_set = queryset.filter(user=self.request.user)
        return query_set

    def perform_create(self, serializer):
        """Метод позволяет автоматически заполнить поля user при создании заказа исходя из переданного токена"""
        serializer.save(user=self.request.user)


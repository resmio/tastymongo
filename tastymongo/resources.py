from django.core.exceptions import ObjectDoesNotExist

from mongoengine import Document

from tastypie.resources import Resource
from tastypie.bundle import Bundle
from tastypie.exceptions import NotFound, InvalidFilterError, BadRequest
from tastypie.constants import ALL
from tastypie.utils import dict_strip_unicode_keys

# Valid query types (a dictionary is used for speedy lookups).
QUERY_TERMS = dict([(x, None) for x in (
    'exact', 'iexact', 'contains', 'icontains', 'gt', 'gte', 'lt', 'lte', 'in',
    'startswith', 'istartswith', 'endswith', 'iendswith', 'range', 'year',
    'month', 'day', 'week_day', 'isnull', 'search', 'regex', 'iregex', 'ne',
)])

LOOKUP_SEP = '__'

class ModelResource(Resource):
    """
    A subclass of Tastypie ``Resource`` designed to work with Mongoengine's ``Models``.
    Blatantly copied and modified from Tastypie's ModelResource.

    """
    def get_resource_uri(self, bundle_or_obj_or_pk=None, url_name='api_dispatch_list'):

        if bundle_or_obj_or_pk is not None:

            kwargs = {
                'resource_name': self._meta.resource_name,
            }

            if isinstance(bundle_or_obj_or_pk, Bundle):
                kwargs['pk'] = str(bundle_or_obj_or_pk.obj.pk) 
            elif isinstance(bundle_or_obj_or_pk, Document):
                kwargs['pk'] = str(bundle_or_obj_or_pk.pk)
            else:
                kwargs['pk'] = bundle_or_obj_or_pk

            if self._meta.api_name is not None:
                kwargs['api_name'] = self._meta.api_name

        return super(ModelResource, self).get_resource_uri(bundle_or_obj=bundle_or_obj_or_pk, url_name=url_name)

    def detail_uri_kwargs(self, bundle_or_obj):
        """
        Given a ``Bundle`` or an object (typically a ``Model`` instance),
        it returns the extra kwargs needed to generate a detail URI.

        By default, it uses the model's ``pk`` in order to create the URI.
        """
        kwargs = {}

        if isinstance(bundle_or_obj, Bundle):
            kwargs[self._meta.detail_uri_name] = getattr(bundle_or_obj.obj, self._meta.detail_uri_name)
        else:
            kwargs[self._meta.detail_uri_name] = getattr(bundle_or_obj, self._meta.detail_uri_name)

        return kwargs

    def obj_get_list(self, request=None, **kwargs):

        filters = {}

        if hasattr(request, 'GET'):
            # Grab a mutable copy.
            filters = request.GET.copy()

        # Update with the provided kwargs.
        filters.update(kwargs)
        applicable_filters = self.build_filters(filters=filters)

        try:
            base_object_list = self.apply_filters(request, applicable_filters)
            return self.apply_authorization_limits(request, base_object_list)
        except ValueError:
            raise BadRequest("Invalid resource lookup data provided (mismatched type).")

    def get_object_list(self, request):
        return self._meta.object_class.objects.all()

    def obj_get(self, request=None, **kwargs):
        """
        A ORM-specific implementation of ``obj_get``.

        Takes optional ``kwargs``, which are used to narrow the query to find
        the instance.
        """
        try:
            base_object_list = self.get_object_list(request).filter(**kwargs)
            object_list = self.apply_authorization_limits(request, base_object_list)
            stringified_kwargs = ', '.join(["%s=%s" % (k, v) for k, v in kwargs.items()])

            if len(object_list) <= 0:
                raise self._meta.object_class.DoesNotExist("Couldn't find an instance of '%s' which matched '%s'." % (self._meta.object_class.__name__, stringified_kwargs))
            elif len(object_list) > 1:
                raise MultipleObjectsReturned("More than '%s' matched '%s'." % (self._meta.object_class.__name__, stringified_kwargs))

            return object_list[0]
        except ValueError:
            raise NotFound("Invalid resource lookup data provided (mismatched type).")

    def obj_create(self, bundle, request=None, **kwargs):
        bundle.obj = self._meta.object_class()

        for key, value in kwargs.items():
            setattr(bundle.obj, key, value)

        bundle = self.full_hydrate(bundle)
        self.is_valid(bundle,request)

        if bundle.errors:
            self.error_response(bundle.errors, request)

        # Save the main object.
        bundle.obj.save()

        return bundle

    def obj_update(self, bundle, request=None, skip_errors=False, **kwargs):

        if not bundle.obj or not bundle.obj.pk:
            # Attempt to hydrate data from kwargs before doing a lookup for the object.
            # This step is needed so certain values (like datetime) will pass model validation.
            try:
                bundle.obj = self._meta.object_class()
                bundle.data.update(kwargs)
                bundle = self.full_hydrate(bundle)
                lookup_kwargs = kwargs.copy()
                lookup_kwargs.update(dict(
                    (k, getattr(bundle.obj, k))
                    for k in kwargs.keys()
                    if getattr(bundle.obj, k) is not None))
            except:
                # if there is trouble hydrating the data, fall back to just
                # using kwargs by itself (usually it only contains a "pk" key
                # and this will work fine.
                lookup_kwargs = kwargs
            try:
                bundle.obj = self.obj_get(request, **lookup_kwargs)
            except ObjectDoesNotExist:
                raise NotFound("A model instance matching the provided arguments could not be found.")

        bundle = self.full_hydrate(bundle)
        self.is_valid(bundle,request)

        if bundle.errors and not skip_errors:
            self.error_response(bundle.errors, request)

        # Save the main object.
        bundle.obj.save()

        cache_key = self.generate_cache_key('detail', **kwargs)
        self._meta.cache.set(cache_key, bundle.obj)

        return bundle

    def obj_delete(self, request=None, **kwargs):

        if hasattr(self._meta.cache, 'delete'):
            cache_key = self.generate_cache_key('detail', **kwargs)
            self._meta.cache.delete(cache_key)

        self._meta.object_class.objects(**kwargs).delete()

    def check_filtering(self, field_name, filter_type='exact', filter_bits=None):
        """
        Given a field name, a optional filter type and an optional list of
        additional relations, determine if a field can be filtered on.

        If a filter does not meet the needed conditions, it should raise an
        ``InvalidFilterError``.

        If the filter meets the conditions, a list of attribute names (not
        field names) will be returned.
        """
        if filter_bits is None:
            filter_bits = []

        if not field_name in self._meta.filtering:
            raise InvalidFilterError("The '%s' field does not allow filtering." % field_name)

        # Check to see if it's an allowed lookup type.
        if not self._meta.filtering[field_name] in (ALL,):
            # Must be an explicit whitelist.
            if not filter_type in self._meta.filtering[field_name]:
                raise InvalidFilterError("'%s' is not an allowed filter on the '%s' field." % (filter_type, field_name))

        if self.fields[field_name].attribute is None:
            raise InvalidFilterError("The '%s' field has no 'attribute' for searching with." % field_name)

        return [self.fields[field_name].attribute]

    def build_filters(self, filters=None):
        """
        Given a dictionary of filters, create the necessary ORM-level filters.

        Keys should be resource fields, **NOT** model fields.

        Valid values are either a list of Django filter types (i.e.
        ``['startswith', 'exact', 'lte']``), the ``ALL`` constant or the
        ``ALL_WITH_RELATIONS`` constant.
        """
        # At the declarative level:
        #     filtering = {
        #         'resource_field_name': ['exact', 'startswith', 'endswith', 'contains'],
        #         'resource_field_name_2': ['exact', 'gt', 'gte', 'lt', 'lte', 'range'],
        #         'resource_field_name_3': ALL,
        #         'resource_field_name_4': ALL_WITH_RELATIONS,
        #         ...
        #     }
        # Accepts the filters as a dict. None by default, meaning no filters.
        if filters is None:
            filters = {}

        qs_filters = {}

        for filter_expr, value in filters.items():
            filter_bits = filter_expr.split(LOOKUP_SEP)
            field_name = filter_bits.pop(0)
            filter_type = 'exact'

            if not field_name in self.fields:
                # It's not a field we know about. Move along citizen.
                continue

            if len(filter_bits) and filter_bits[-1] in QUERY_TERMS.keys():
                filter_type = filter_bits.pop()

            lookup_bits = self.check_filtering(field_name, filter_type, filter_bits)

            if value in ['true', 'True', True]:
                value = True
            elif value in ['false', 'False', False]:
                value = False
            elif value in ('nil', 'none', 'None', None):
                value = None

            # Split on ',' if not empty string and either an in or range filter.
            if filter_type in ('in', 'range') and len(value):
                if hasattr(filters, 'getlist'):
                    value = filters.getlist(filter_expr)
                else:
                    value = value.split(',')

            db_field_name = LOOKUP_SEP.join(lookup_bits)
            qs_filter = "%s%s%s" % (db_field_name, LOOKUP_SEP, filter_type)
            qs_filters[qs_filter] = value

        return dict_strip_unicode_keys(qs_filters)

    def apply_filters(self, request, applicable_filters):
        """
        An ORM-specific implementation of ``apply_filters``.

        The default simply applies the ``applicable_filters`` as ``**kwargs``,
        but should make it possible to do more advanced things.
        """
        return self.get_object_list(request).filter(**applicable_filters)

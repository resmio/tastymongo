from django.core.urlresolvers import resolve, Resolver404, get_script_prefix

from tastypie.fields import RelatedField
from tastypie.exceptions import ApiFieldError
from tastypie.exceptions import NotFound

class NOT_PROVIDED:
    pass

class RelatedUriField(RelatedField):
    """
    Used for mapping between a resource uri and the manual link to the related data
      - /myresource/123 -> 123
      - 123 -> /myresource/123

    """
    def __init__(self, to, attribute, related_name=None, default=NOT_PROVIDED,
                 null=False, blank=False, readonly=False, full=False,
                 unique=False, help_text=None):
        super(RelatedUriField, self).__init__(
            to, attribute, related_name=related_name, default=default,
            null=null, blank=False, readonly=False, full=full, unique=unique, help_text=help_text
        )
        self.fk_resource = None
        self.is_related = False # we are no really a related field

    def resource_id_from_uri(self, fk_resource, uri, request=None, related_obj=None, related_name=None):
        """
        Given a URI is provided, the related resource id is returned.
        """
        prefix = get_script_prefix()
        chomped_uri = uri

        if prefix and chomped_uri.startswith(prefix):
            chomped_uri = chomped_uri[len(prefix)-1:]

        try:
            view, args, kwargs = resolve(chomped_uri)
            return kwargs['pk']
        except Resolver404:
            raise NotFound("The URL provided '%s' was not a link to a valid resource." % uri)

    def dehydrate(self, bundle):

        related_id = getattr(bundle.obj, self.attribute)

        if not related_id:
            if not self.null:
                raise ApiFieldError("The model '%r' has an empty attribute '%s' and doesn't allow a null value." % (bundle.obj, self.attribute))

            return None

        self.fk_resource = self.to_class()

        return self.fk_resource.get_resource_uri(related_id)

    def hydrate(self, bundle):

        value = super(RelatedUriField, self).hydrate(bundle)

        self.fk_resource = self.to_class()

        if isinstance(value, basestring):
            # We got a URI. Load the object and assign it.
            return self.resource_id_from_uri(self.fk_resource, value)

        raise ApiFieldError("The '%s' field was given data that was not a URI: %s." % (self.instance_name, value))

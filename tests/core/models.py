from mongoengine import Document, StringField

from tastymongo.fields import RelatedUriField

class Event(Document):
    title = StringField()

class Booking(Document):
    event = RelatedUriField('core.models.event', 'event')
    name = StringField()

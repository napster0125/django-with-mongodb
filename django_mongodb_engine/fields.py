from django.core.exceptions import ImproperlyConfigured
from django.db import connections, models

from pymongo.objectid import ObjectId
from gridfs import GridFS

from djangotoolbox.fields import EmbeddedModelField as _EmbeddedModelField
from django_mongodb_engine.utils import make_struct

__all__ = ['LegacyEmbeddedModelField', 'GridFSField', 'GridFSString']

class LegacyEmbeddedModelField(_EmbeddedModelField):
    """
    Wrapper around djangotoolbox' :class:`EmbeddedModelField` that keeps
    backwards compatibility with data generated by django-mongodb-engine < 0.3.
    """
    def to_python(self, values):
        if isinstance(values, dict):
            # In version 0.2, the layout of the serialized model instance changed.
            # Cleanup up old instances from keys that aren't used any more.
            values.pop('_app', None)
            if '_module' not in values:
                values.pop('_model', None)
            # Up to version 0.2, '_id's were added automatically.
            # Keep backwards compatibility to old data records.
            if '_id' in values:
                values['id'] = values.pop('_id')
        return super(LegacyEmbeddedModelField, self).to_python(values)

class GridFSField(models.Field):
    """
    GridFS field to store large chunks of data (blobs) in GridFS.

    Model instances keep references (ObjectIds) to GridFS files
    (:class:`grifs.GridOut`) which are fetched on first attribute access.

    :param delete:
        Whether to delete the data stored in the GridFS (as GridFS files) when
        model instances are deleted (default: :const:`True`).
    :param versioning:
        Whether to keep old versions of the data when new data is written to the
        GridFS (default: :const:`False`).
        `delete` and `versioning` are mutually exclusive.
    """
    forbids_updates = True

    def __init__(self, *args, **kwargs):
        self._versioning = kwargs.pop('versioning', False)
        self._autodelete = kwargs.pop('delete', not self._versioning)
        if self._versioning and self._autodelete:
            raise ImproperlyConfigured("Can have only one of 'versioning' and 'delete'")

        kwargs['max_length'] = 24
        kwargs.setdefault('default', None)
        kwargs.setdefault('null', True)
        super(GridFSField, self).__init__(*args, **kwargs)

    def db_type(self, connection):
        return 'gridfs'

    def contribute_to_class(self, model, name):
        # GridFSFields are represented as properties in the model class.
        # Let 'foo' be an instance of a model that has the GridFSField 'gridf'.
        # 'foo.gridf' then calls '_property_get' and 'foo.gridfs = bar' calls
        # '_property_set(bar)'.
        super(GridFSField, self).contribute_to_class(model, name)
        setattr(model, self.attname, property(self._property_get, self._property_set))
        if self._autodelete:
            models.signals.pre_delete.connect(self._on_pre_delete, sender=model)

    def _property_get(self, model_instance):
        """
        Gets the file from GridFS using the id stored in the model.
        """
        meta = self._get_meta(model_instance)
        if meta.filelike is None and meta.oid is not None:
            gridfs = self._get_gridfs(model_instance)
            meta.filelike = gridfs.get(meta.oid)
        return meta.filelike

    def _property_set(self, model_instance, value):
        """
        Sets a new value.

        If value is an ObjectID it must be coming from Django's ORM internals
        being the value fetched from the database on query. In that case just
        update the id stored in the model instance.
        Otherwise it sets the value and checks whether a save is needed or not.
        """
        meta = self._get_meta(model_instance)
        if isinstance(value, ObjectId) and meta.oid is None:
            meta.oid = value
        else:
            meta.should_save = meta.filelike != value
            meta.filelike = value

    def pre_save(self, model_instance, add):
        meta = self._get_meta(model_instance)
        if meta.should_save:
            gridfs = self._get_gridfs(model_instance)
            if not self._versioning and meta.oid is not None:
                # We're putting a new GridFS file, so get rid of the old one
                # if we weren't explicitly asked to keep it.
                gridfs.delete(meta.oid)
            return gridfs.put(meta.filelike)
        return meta.oid

    def _on_pre_delete(self, sender, instance, using, signal, **kwargs):
        self._get_gridfs(instance).delete(self._get_meta(instance).oid)

    def _get_meta(self, model_instance):
        meta_name = '_%s_meta' % self.attname
        meta = getattr(model_instance, meta_name, None)
        if meta is None:
            meta_cls = make_struct('filelike', 'oid', 'should_save')
            meta = meta_cls(None, None, None)
            setattr(model_instance, meta_name, meta)
        return meta

    def _get_gridfs(self, model_instance):
        return GridFS(connections[model_instance.__class__.objects.db].database)

class GridFSString(GridFSField):
    """
    Similar to :class:`GridFSField`, but the data is represented as a bytestring
    on Python side. This implies that all data has to be copied **into memory**,
    so :class:`GridFSString` is for smaller chunks of data only.
    """
    def _property_get(self, model):
        filelike = super(GridFSString, self)._property_get(model)
        if filelike is None:
            return ''
        if hasattr(filelike, 'read'):
            return filelike.read()
        return filelike

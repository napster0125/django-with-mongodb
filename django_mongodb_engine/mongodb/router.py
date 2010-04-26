
class MongoDBRouter(object):
    """A router to control all database operations on models in
    the myapp application"""
    def __init__(self):
        from django.conf import settings
        self.managed_apps = [app.split('.')[-1] for app in getattr(settings, "MONGODB_MANAGED_APPS", [])]
        self.mongodb_database = None
        self.mongodb_databases = []
        for name, databaseopt in settings.DATABASES.items():
            if databaseopt["ENGINE"]=='django_mongodb_engine.mongodb':
                self.mongodb_database = name
                self.mongodb_databases.append(name)
        if self.mongodb_database is None:
            raise RuntimeError("A mongodb database must be set")

    def db_for_read(self, model, **hints):
        "Point all operations on mongodb models to a mongodb database"
        if model._meta.app_label in self.managed_apps:
            return self.mongodb_database
        return None

    def db_for_write(self, model, **hints):
        "Point all operations on mongodb models to a mongodb database"
        if model._meta.app_label in self.managed_apps:
            return self.mongodb_database
        return None

    def allow_relation(self, obj1, obj2, **hints):
        "Allow any relation if a model in myapp is involved"
        if obj1._meta.app_label in self.managed_apps or obj2._meta.app_label in self.managed_apps:
            return False
        return None

    def allow_syncdb(self, db, model):
        "Make sure that a mongodb model appears on a mongodb database"
        if db in self.mongodb_databases:
            return model._meta.app_label  in self.managed_apps
        elif model._meta.app_label in self.managed_apps:
            return False
        return None

    def valid_for_db_engine(self, driver, model):
        "Make sure that a model is valid for a database provider"
        if driver!="django.db.backends.mongodb":
            return None
        if model._meta.app_label in self.managed_apps:
            return True
        return None
        

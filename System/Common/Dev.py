from loguru import logger

def track_ram(cls):
    orig_delete = getattr(cls, "__del__", None)

    def new_del(self):
        class_name = self.__class__.__name__
        #logger.success(f"{class_name} {id(self)} has been deleted from RAM")
        
        if orig_delete is not None:
            orig_delete(self)

    cls.__del__ = new_del
    return cls
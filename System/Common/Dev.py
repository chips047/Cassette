from loguru import logger

def track_ram(cls):
    orig_del = getattr(cls, "__del__", None)

    def new_del(self):
        class_name = self.__class__.__name__
        logger.success(f"{class_name} {id(self)} has been deleted from RAM")
        
        if orig_del is not None:
            orig_del(self)

    cls.__del__ = new_del
    return cls
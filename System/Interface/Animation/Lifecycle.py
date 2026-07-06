import weakref
from PyQt6.QtCore import pyqtSlot
from System.Interface.Animation import LoomEngine

class LoomAnimationMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._engine_acquired = False
        
        if hasattr(self, 'destroyed'):
            weak_self = weakref.ref(self)
            self.destroyed.connect(lambda: LoomAnimationMixin._safe_cleanup(weak_self))

    def showEvent(self, event):
        super().showEvent(event)
        if not self._engine_acquired:
            LoomEngine.ui_engine.acquire()
            self._engine_acquired = True

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._engine_acquired:
            LoomEngine.ui_engine.release()
            self._engine_acquired = False

    @staticmethod
    def _safe_cleanup(weak_self):
        obj = weak_self()
        
        if obj is not None:
            if obj._engine_acquired:
                LoomEngine.ui_engine.release()
                obj._engine_acquired = False
            
            LoomEngine.ui_engine.unbind_owner(obj)

def classFactory(iface):
    from .plugin import MtrExamplePlugin
    return MtrExamplePlugin(iface)

class torturedevice:
    func_shock		= False
    func_vibe		= False
    func_piep   	= False
    func_stretch	= False
    func_switch		= False

    uuid_device		= ""
    uuid_model		= ""
    ip_address		= ""
    status		= False

    def __init__(self, model, device, ip_address, status):
        self.uuid_device	= device
        self.uuid_model 	= model
        self.ip_address	    = ip_address
        self.status		    = status

        if model == "eaa4cae0-65d6-4cf2-80ef-d8d0f8e8f6f0":
            self.func_shock		= True
            self.func_stretch	= True

        if model == "73903cef-049d-4439-a9ab-f05825e0ef25":
            self.func_shock		= True
            self.func_vibe		= True
            self.func_piep		= True

    def get_device(self):
        return self.uuid_device

    def inital_settings(self):
        pass

    def shock(self, seconds, countdown):
        if self.func_shock == True:
            command = "{"seconds": '+str(seconds)+', "countdown": '+str(countdown)+'}"
        else:
            command = None
        return command

    def vibe(self):
        pass

    def piep(self):
        pass

    def stretch(self):
        pass

    def switch(self):
        pass


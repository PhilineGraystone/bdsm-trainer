class torturedevice:
    func_shock		= False
    func_vibe		= False
    func_piep   	= False
    func_stretch	= False
    func_switch		= False
    func_lock		= False
    func_blowjob    = False

    mode_pet        = False
    mode_wlan_fence = False
    mode_sleep_dep  = False
    mode_remote     = False

    device_collar   = False

    uuid_device		= ""
    uuid_model		= ""
    uuid_name       = ""
    ip_address		= ""
    status		    = False

    mqtt            = None

    owner           = None
    registred       = None
    last_response   = None

    def __init__(self, mqtt, model, device, ip_address, status):
        self.mqtt           = mqtt

        self.uuid_device	= device
        self.uuid_model 	= model
        self.ip_address	    = ip_address
        self.status		    = status
        self.owner          = False
        self.registered     = False

        if model == "eaa4cae0-65d6-4cf2-80ef-d8d0f8e8f6f0":
            self.uuid_name      = "Stretcher and Shocker"
            self.func_shock		= True
            self.func_stretch	= True

        if model == "73903cef-049d-4439-a9ab-f05825e0ef25":
            self.uuid_name      = "Collar v1.0"
            self.func_shock		= True
            self.func_vibe		= True
            self.func_piep		= True
            self.mode_pet       = True
            self.mode_wlan_fence= True
            self.mode_sleep_dep = True
            self.mode_remote    = True
            self.device_collar  = True

        if model == "1acf784c-4bfd-4a06-b4ff-ee578a37fac4":
            self.func_lock      = True

        if model == "4f1fb373-8cca-492b-a619-2e53318d2493":
            self.uuid_name      = "Blowjob Trainer V2.0";
            self.func_blowjob	= True

    def get_device(self):
        return self.uuid_device

    def inital_settings(self):
        pass

    def shock(self, seconds, countdown):
        if self.func_shock == True:
            self.mqtt.publish('punisher/devices/'+str(self.uuid_device)+'/shock', '{"seconds": '+str(seconds)+', "countdown": '+str(countdown)+'}' )

    def vibe(self):
        pass

    def piep(self):
        pass

    def stretch(self):
        pass

    def switch(self):
        pass

    def blowjob(self, wait, jobcounter, punishment, delay):
        if self.func_blowjob == True:
            self.mqtt.publish('punisher/devices/'+str(self.uuid_device)+'/blowjob', '{"wait": '+str(wait)+', "count": '+str(jobcount)+', "punishment": '+str(punishment)+', "delay": '+str(delay)+'}' )

    def pet(self):
        if self.mode_pet == True:
            self.mqtt.publish('punisher/devices/'+str(self.uuid_device)+'/settings', '{"mode": 4}' )

    def wlan_fence(self):
        if self.mode_wlan_fence == True:
            self.mqtt.publish('punisher/devices/'+str(self.uuid_device)+'/settings', '{"mode": 1}' )

    def sleep_deprivation(self):
        if self.mode_sleep_dep == True:
            self.mqtt.publish('punisher/devices/'+str(self.uuid_device)+'/settings', '{"mode": 3}' )

    def remote_control(self):
        if self.mode_remote == True:
            self.mqtt.publish('punisher/devices/'+str(self.uuid_device)+'/settings', '{"mode": 0}' )

    def maglock(self, minutes):
        if self.func_lock == True:
            self.mqtt.publish('punisher/devices/'+str(self.uuid_device)+'/lock', '{"minutes": '+str(minutes)+'}' )

    def collar_settings(self, shock, vibe, beep, duration):
        if self.device_collar == True:
            self.mqtt.publish('punisher/devices/'+str(self.uuid_device)+'/settings', '{"shock": '+str(shock)+', "vibe": '+str(vibe)+', "beep": '+str(beep)+', "duration": '+str(duration)+'}' )

    def set_response(self, response):
        self.last_response = response

    def get_response(self):
        return self.last_response


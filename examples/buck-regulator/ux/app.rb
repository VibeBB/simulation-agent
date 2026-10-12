# UX power-good indicator: drive the status LEDs through the device API
# stub while the buck regulator analysis runs. Stub calls log to the
# transcript so `expect` lines assert the device-API surface.
LED.set(part: :led1, state: true)
LED.toggle(:led1)
puts "buck ux ready"

#include <Arduino.h>

#include "app/application.hpp"

#ifndef PIO_UNIT_TESTING

void setup() { (void)mocap::app::application().begin(); }

void loop() { mocap::app::application().poll(); }

#endif

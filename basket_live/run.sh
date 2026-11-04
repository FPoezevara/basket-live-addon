#!/usr/bin/with-contenv bashio
# Identifiants Mosquitto fournis par le Supervisor (services: mqtt:need)

if ! bashio::services.available "mqtt"; then
    bashio::exit.nok "Aucun broker MQTT disponible : installer et démarrer Mosquitto."
fi

export MQTT_HOST="$(bashio::services mqtt 'host')"
export MQTT_PORT="$(bashio::services mqtt 'port')"
export MQTT_USER="$(bashio::services mqtt 'username')"
export MQTT_PASSWORD="$(bashio::services mqtt 'password')"

bashio::log.info "Démarrage de Basket Live (broker ${MQTT_HOST}:${MQTT_PORT})"
cd /opt/basket_live || exit 1
exec python3 -m app.main

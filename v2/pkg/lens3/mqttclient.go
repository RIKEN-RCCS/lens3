/* MQTT Client for Event Notification. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Lens3 uses Paho for MQTT v5.  Do not confuse Paho for v3 with v5.

// MQTT V3
// https://pkg.go.dev/github.com/eclipse/paho.mqtt.golang
// MQTT V5
// https://pkg.go.dev/github.com/eclipse/paho.golang

// MEMO: Setup passwords for mosquitto
//
// % mosquitto_passwd -c password.txt lens3
// % mosquitto_passwd -b password.txt lens3 password
//
// # vi /etc/mosquitto/mosquitto.conf
//   allow_anonymous false
//   password_file /etc/mosquitto/password.txt

import (
	"context"
	"fmt"
	"github.com/eclipse/paho.golang/autopaho"
	"github.com/eclipse/paho.golang/autopaho/queue/memory"
	"github.com/eclipse/paho.golang/paho"
	"net/url"
	"time"
	//"github.com/eclipse/paho.mqtt.golang"
	//"os"
	//"os/signal"
	//"strconv"
	//"syscall"
)

type mqtt_client struct {
	ch_quit_service <-chan vacuous
	cm              *autopaho.ConnectionManager
	queue           *memory.Queue
	conf            *mqtt_conf
}

func configure_mqtt(c *mqtt_conf, qch <-chan vacuous) *mqtt_client {
	var q = &mqtt_client{}
	q.conf = c
	q.ch_quit_service = qch
	var ep = "mqtt://" + q.conf.Ep
	var mqtturl, err1 = url.Parse(ep)
	if err1 != nil {
		slogger.Error("MQTT() Bad endpoint", "ep", ep, "err", err1,
			"alert", true)
		return nil
	}
	q.queue = memory.New()
	var conf = autopaho.ClientConfig{
		Queue: q.queue,

		ServerUrls: []*url.URL{mqtturl},

		KeepAlive: 300,

		CleanStartOnInitialConnection: false,

		SessionExpiryInterval: 60,

		OnConnectionUp: func(cm *autopaho.ConnectionManager, ack *paho.Connack) {
			slogger.Debug("MQTT() Connection up", "ack", ack.ReasonCode,
				"alert", true)
		},

		OnConnectError: func(err error) {
			slogger.Warn("MQTT() Connection failed", "err", err,
				"alert", true)
		},

		ConnectUsername: q.conf.Username,
		ConnectPassword: []byte(q.conf.Password),

		ClientConfig: paho.ClientConfig{

			ClientID: q.conf.Client,

			//Session:

			OnPublishReceived: []func(paho.PublishReceived) (bool, error){},

			OnClientError: func(err error) {
				slogger.Warn("MQTT() Client error", "err", err,
					"alert", true)
			},

			OnServerDisconnect: func(d *paho.Disconnect) {
				if d.Properties != nil {
					slogger.Debug("MQTT() Server disconnect",
						"reason", d.Properties.ReasonString,
						"alert", true)
				} else {
					slogger.Debug("MQTT() Server disconnect",
						"code", d.ReasonCode,
						"alert", true)
				}
			},
		},
	}
	var ctx = context.Background()
	var cm, err2 = autopaho.NewConnection(ctx, conf)
	if err2 != nil {
		slogger.Error("MQTT() paho.NewConnection() failed", "err", err2,
			"alert", true)
		return nil
	}
	q.cm = cm
	var err3 = cm.AwaitConnection(ctx)
	if err3 != nil {
		slogger.Error("MQTT() paho.AwaitConnection() failed", "err", err3,
			"alert", true)
		return nil
	}

	//go mqtt_client_test__(q)

	return q
}

func pub_mqtt_message(q *mqtt_client, m string) error {
	var ctx = context.Background()
	// q.cm.Publish(ctx, &paho.Publish{})
	var err1 = q.cm.PublishViaQueue(ctx, &autopaho.QueuePublish{
		Publish: &paho.Publish{
			QoS:     0,
			Topic:   q.conf.Topic,
			Payload: []byte(m),
		},
	})
	if err1 != nil {
		if ctx.Err() == nil {
			slogger.Error("MQTT() paho.Publish() failed", "err", err1,
				"alert", true)
		}
	}
	return err1
}

func (q *mqtt_client) Write(m []byte) (int, error) {
	var len = len(m)
	var err = pub_mqtt_message(q, string(m))
	return len, err
}

func mqtt_client_test__(q *mqtt_client) {
	var ticker = time.NewTicker(time.Second)
	defer ticker.Stop()
	var count = 0
	for count < 20 {
		select {
		case <-ticker.C:
			fmt.Println("tick")
			count++
			pub_mqtt_message(q, fmt.Sprintf("count=%d", count))
			continue
		}
	}
}

# Ein etcd-Bild fuer den Zwischenschritt 3.5.13 → 3.6.
#
# Warum es das gibt:
#
# etcd verlangt vor dem Sprung auf 3.6, dass **alle** Mitglieder auf 3.5.32
# oder neuer stehen (etcd.io/docs/v3.6/upgrades/upgrade_3_6). Unsere hosted
# Steuerungsebenen fahren `quay.io/k0sproject/etcd:v3.5.13`, und dieses
# Repository fuehrt genau drei Tags: v3.5.13, v3.6.14, v3.7.1. Die
# Zwischenstufe fehlt also.
#
# Die offiziellen etcd-Bilder haben sie, aber **keine Shell** (geprueft):
#
#   quay.io/coreos/etcd:v3.5.36     /bin/bash fehlt, /bin/sh fehlt
#   registry.k8s.io/etcd:3.5.32-0   /bin/bash fehlt, /bin/sh fehlt
#
# Und k0smotron verdrahtet den etcd-Container fest auf eine bash:
#
#   Command: ["/bin/bash"], Args: ["-c", <Einstiegsskript>]
#   (internal/controller/k0smotron.io/k0smotroncluster_etcd.go)
#
# `spec.etcd.args` werden *in* dieses Skript gehaengt und ersetzen das
# Kommando nicht. Ein Bild ohne bash startet damit gar nicht.
#
# Deshalb: dasselbe Bild wie bisher, nur mit neueren Binaerdateien. Basis,
# Pfade, Benutzer und Einstiegspunkt bleiben, wie k0smotron sie erwartet -
# geaendert wird eine Sache, nicht zwei.

# Die letzte 3.5er Fassung. Sie ist das Ziel des Zwischenschritts, nicht der
# Dauerzustand: nach 3.6.14 und weiter auf 3.7.1 wird dieses Bild nicht mehr
# gebraucht.
ARG ETCD_VERSION=v3.5.36

# ---- holen und pruefen ------------------------------------------------------
#
# Eine eigene Stufe, weil das Basisbild weder curl noch wget hat - und `ADD`
# mit einer URL braucht beides nicht.
FROM debian:12-slim AS holen
ARG ETCD_VERSION
ARG TARGETARCH=amd64

ADD https://github.com/etcd-io/etcd/releases/download/${ETCD_VERSION}/etcd-${ETCD_VERSION}-linux-${TARGETARCH}.tar.gz /tmp/etcd.tar.gz
ADD https://github.com/etcd-io/etcd/releases/download/${ETCD_VERSION}/SHA256SUMS /tmp/SHA256SUMS

# Die Pruefsumme gegen die veroeffentlichte Liste. Das ist hier keine
# Formalie: diese Binaerdatei laeuft in der Steuerungsebene eines
# Kundenclusters, und sie kommt nicht aus unserem Bau.
RUN set -eux; \
    cd /tmp; \
    name="etcd-${ETCD_VERSION}-linux-${TARGETARCH}.tar.gz"; \
    cp etcd.tar.gz "$name"; \
    grep " $name\$" SHA256SUMS | sha256sum -c -; \
    mkdir -p /bin-neu; \
    tar xzf "$name" -C /bin-neu --strip-components=1 \
      "etcd-${ETCD_VERSION}-linux-${TARGETARCH}/etcd" \
      "etcd-${ETCD_VERSION}-linux-${TARGETARCH}/etcdctl" \
      "etcd-${ETCD_VERSION}-linux-${TARGETARCH}/etcdutl"

# ---- einsetzen --------------------------------------------------------------
FROM quay.io/k0sproject/etcd:v3.5.13
ARG ETCD_VERSION

USER root
# Genau die drei, die das Bild schon fuehrt - nichts dazu, nichts weg.
COPY --from=holen --chmod=0755 /bin-neu/etcd    /opt/bitnami/etcd/bin/etcd
COPY --from=holen --chmod=0755 /bin-neu/etcdctl /opt/bitnami/etcd/bin/etcdctl
COPY --from=holen --chmod=0755 /bin-neu/etcdutl /opt/bitnami/etcd/bin/etcdutl

# Beweis im Bauprotokoll, nicht erst im Cluster: die Fassung stimmt, und die
# bash ist noch da - ohne sie startet k0smotrons Einstiegsskript nicht.
RUN set -eux; \
    /opt/bitnami/etcd/bin/etcd --version; \
    test -x /bin/bash

# Wie im Basisbild: etcd laeuft nicht als root.
USER 1001

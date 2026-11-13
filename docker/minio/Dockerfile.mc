# syntax=docker/dockerfile:1
# minio/mc is no longer published on Docker Hub; build the last release from source.
FROM golang:1.24-alpine AS build
ARG MC_RELEASE_TAG=RELEASE.2025-08-13T08-35-41Z
RUN apk add --no-cache git
RUN git clone --depth 1 --branch "${MC_RELEASE_TAG}" https://github.com/minio/mc.git /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath \
      -ldflags "$(MC_RELEASE=RELEASE go run buildscripts/gen-ldflags.go "${MC_RELEASE_TAG#RELEASE.}")" \
      -o /out/mc .

FROM alpine:3.22
RUN apk add --no-cache ca-certificates
COPY --from=build /out/mc /usr/bin/mc
ENTRYPOINT ["/usr/bin/mc"]

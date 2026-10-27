import QtQuick
Rectangle {
    id: surface
    property color shadowTone: "transparent"
    color: "#fffef5"
    radius: 15
    border.color: "#101d42"
    border.width: 2
    antialiasing: true
    Rectangle { z: -1; x: 4; y: 5; width: surface.width; height: surface.height; radius: surface.radius; color: surface.shadowTone; antialiasing: true }
}

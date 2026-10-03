-- Cinematic camera route and free-fly camera controls.

local tourActive = false
local tourIndex = 1
local tourElapsed = 0
local tourAnchorX, tourAnchorY, tourAnchorZ = 0, 0, 0
local freeActive = false
local freeCamera = nil
local lastCursorX, lastCursorY = nil, nil

local function tourMessage(text)
    outputChatBox("[NightCity] " .. text, 120, 220, 255, true)
end

local function stopTour(finished)
    if not tourActive then
        return
    end
    tourActive = false
    removeEventHandler("onClientPreRender", root, updateTourCamera)
    unbindKey("space", "down", stopTourKey)
    unbindKey("backspace", "down", stopTourKey)
    setCameraTarget(localPlayer)
    setElementFrozen(localPlayer, false)
    if finished then
        tourMessage("tour finished.")
    end
end

function stopTourKey()
    stopTour(false)
end

function updateTourCamera(timeSlice)
    if not tourActive then
        return
    end
    local count = #NC_TOUR
    if count < 2 then
        stopTour(true)
        return
    end
    tourElapsed = tourElapsed + math.max(0, tonumber(timeSlice) or 0)
    while tourIndex < count do
        local duration = math.max(0.01, tonumber(NC_TOUR[tourIndex][7]) or 1)
        if tourElapsed < duration then
            break
        end
        tourElapsed = tourElapsed - duration
        tourIndex = tourIndex + 1
    end
    if tourIndex >= count then
        local last = NC_TOUR[count]
        setCameraMatrix(tourAnchorX + last[1], tourAnchorY + last[2], tourAnchorZ + last[3],
                        tourAnchorX + last[4], tourAnchorY + last[5], tourAnchorZ + last[6])
        stopTour(true)
        return
    end
    local a, b = NC_TOUR[tourIndex], NC_TOUR[tourIndex + 1]
    local duration = math.max(0.01, tonumber(a[7]) or 1)
    local t = math.max(0, math.min(1, tourElapsed / duration))
    local x = a[1] + (b[1] - a[1]) * t
    local y = a[2] + (b[2] - a[2]) * t
    local z = a[3] + (b[3] - a[3]) * t
    local tx = a[4] + (b[4] - a[4]) * t
    local ty = a[5] + (b[5] - a[5]) * t
    local tz = a[6] + (b[6] - a[6]) * t
    setCameraMatrix(tourAnchorX + x, tourAnchorY + y, tourAnchorZ + z,
                    tourAnchorX + tx, tourAnchorY + ty, tourAnchorZ + tz)
end

function NC_StopTour(finished)
    stopTour(finished == true)
end

local function commandTour()
    if tourActive then
        stopTour(false)
        return
    end
    if not NC_IsCityVisible() then
        tourMessage("show the city first with /ncshow.")
        return
    end
    if freeActive then
        NC_StopFreeCamera(false)
    end
    local x, y, z, dz = NC_GetCityAnchor()
    tourAnchorX, tourAnchorY, tourAnchorZ = x, y, z + dz
    tourIndex, tourElapsed = 1, 0
    tourActive = true
    setElementFrozen(localPlayer, true)
    bindKey("space", "down", stopTourKey)
    bindKey("backspace", "down", stopTourKey)
    addEventHandler("onClientPreRender", root, updateTourCamera)
    updateTourCamera(0)
end

local function stopFreeCamera(restorePlayer)
    if not freeActive then
        return
    end
    freeActive = false
    removeEventHandler("onClientPreRender", root, updateFreeCamera)
    removeEventHandler("onClientCursorMove", root, rotateFreeCamera)
    freeCamera = nil
    lastCursorX, lastCursorY = nil, nil
    if restorePlayer ~= false then
        setCameraTarget(localPlayer)
        setElementFrozen(localPlayer, false)
    end
end

function NC_StopFreeCamera(restorePlayer)
    stopFreeCamera(restorePlayer)
end

function rotateFreeCamera(relativeX, relativeY, absoluteX, absoluteY)
    if not freeActive or not freeCamera then
        return
    end
    absoluteX, absoluteY = tonumber(absoluteX), tonumber(absoluteY)
    if not absoluteX or not absoluteY then
        return
    end
    if not lastCursorX then
        lastCursorX, lastCursorY = guiGetScreenSize()
    end
    local dx, dy = absoluteX - lastCursorX, absoluteY - lastCursorY
    lastCursorX, lastCursorY = absoluteX, absoluteY
    freeCamera.yaw = freeCamera.yaw + dx * 0.003
    freeCamera.pitch = math.max(-1.35, math.min(1.35, freeCamera.pitch - dy * 0.002))
end

function updateFreeCamera(timeSlice)
    if not freeActive or not freeCamera then
        return
    end
    local dt = math.max(0, math.min(0.1, tonumber(timeSlice) or 0))
    local speed = getKeyState("lshift") and 80 or 20
    local forward = (getKeyState("w") and 1 or 0) - (getKeyState("s") and 1 or 0)
    local strafe = (getKeyState("d") and 1 or 0) - (getKeyState("a") and 1 or 0)
    local vertical = (getKeyState("e") and 1 or 0) - (getKeyState("q") and 1 or 0)
    local fx, fy = math.cos(freeCamera.yaw), math.sin(freeCamera.yaw)
    local rx, ry = -fy, fx
    freeCamera.x = freeCamera.x + (fx * forward + rx * strafe) * speed * dt
    freeCamera.y = freeCamera.y + (fy * forward + ry * strafe) * speed * dt
    freeCamera.z = freeCamera.z + vertical * speed * dt
    local cp = math.cos(freeCamera.pitch)
    local lx = freeCamera.x + math.cos(freeCamera.yaw) * cp
    local ly = freeCamera.y + math.sin(freeCamera.yaw) * cp
    local lz = freeCamera.z + math.sin(freeCamera.pitch)
    setCameraMatrix(freeCamera.x, freeCamera.y, freeCamera.z, lx, ly, lz)
end

local function commandFreeCamera()
    if freeActive then
        stopFreeCamera(true)
        return
    end
    if not NC_IsCityVisible() then
        tourMessage("show the city first with /ncshow.")
        return
    end
    if tourActive then
        stopTour(false)
    end
    local x, y, z, lx, ly, lz = getCameraMatrix()
    local dx, dy, dz = lx - x, ly - y, lz - z
    freeCamera = {
        x = x, y = y, z = z,
        yaw = math.atan2(dy, dx),
        pitch = math.atan2(dz, math.sqrt(dx * dx + dy * dy))
    }
    freeActive = true
    setElementFrozen(localPlayer, true)
    addEventHandler("onClientPreRender", root, updateFreeCamera)
    addEventHandler("onClientCursorMove", root, rotateFreeCamera)
    lastCursorX, lastCursorY = guiGetScreenSize()
end

addCommandHandler("nctour", commandTour)
addCommandHandler("ncfree", commandFreeCamera)

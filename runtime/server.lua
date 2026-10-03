-- NightCity server control.  The generated city is client-rendered and is only
-- shown to a player when an administrator (or the player, with the default
-- ADMIN_ONLY setting) requests it.
ADMIN_ONLY = false

local cityAnchors = {}
local emptyTimer = nil

local function tell(player, message)
    if isElement(player) then
        outputChatBox("[NightCity] " .. message, player, 120, 220, 255, true)
    end
end

local function isAllowed(player)
    if not ADMIN_ONLY then
        return true
    end
    if not isElement(player) then
        return false
    end
    local account = getPlayerAccount(player)
    if not account or isGuestAccount(account) then
        return false
    end
    local group = aclGetGroup("Admin")
    return group ~= false and isObjectInACLGroup("user." .. getAccountName(account), group)
end

local function deny(player)
    tell(player, "not allowed; an Admin ACL account is required.")
end

local function sendHide(player)
    if isElement(player) then
        triggerClientEvent(player, "nc:hide", resourceRoot)
    end
end

addEvent("nc:ready", true)
addEventHandler("nc:ready", resourceRoot, function()
    if not client then
        return
    end
    -- A client may have reconnected while stale local objects were still present.
    sendHide(client)
end)

addCommandHandler("ncshow", function(player, commandName, arg1, arg2, arg3)
    if not isAllowed(player) then
        deny(player)
        return
    end
    local ax, ay, az = 0, 0, 900
    if arg1 and string.lower(tostring(arg1)) == "here" then
        local x, y, z = getElementPosition(player)
        local spawn = NC_POINTS.spawn
        ax, ay, az = x - spawn[1], y - spawn[2], z - spawn[3]
    elseif arg1 ~= nil then
        local x, y, z = tonumber(arg1), tonumber(arg2), tonumber(arg3)
        if not x or not y or not z then
            tell(player, "usage: /ncshow [here | x y z]")
            return
        end
        ax, ay, az = x, y, z
    end
    cityAnchors[player] = { x = ax, y = ay, z = az }
    triggerClientEvent(player, "nc:show", resourceRoot, ax, ay, az)
end)

addCommandHandler("nchide", function(player)
    if not isAllowed(player) then
        deny(player)
        return
    end
    cityAnchors[player] = nil
    sendHide(player)
end)

addCommandHandler("ncz", function(player, commandName, amount)
    if not isAllowed(player) then
        deny(player)
        return
    end
    local dz = tonumber(amount)
    if not dz then
        tell(player, "Usage: /ncz <metres> (each change is limited to 8 m).")
        return
    end
    dz = math.max(-8, math.min(8, dz))
    triggerClientEvent(player, "nc:z", resourceRoot, dz)
    if cityAnchors[player] then
        cityAnchors[player].z = cityAnchors[player].z + dz
    end
end)

local function emptyCity(anchor)
    anchor = anchor or { x = 0, y = 0, z = 900 }
    local margin = 80
    local x0, x1 = anchor.x + NC_EXTENT.x0 - margin, anchor.x + NC_EXTENT.x1 + margin
    local y0, y1 = anchor.y + NC_EXTENT.y0 - margin, anchor.y + NC_EXTENT.y1 + margin
    local z0, z1 = anchor.z - 80, anchor.z + 500
    local removed = 0
    for _, kind in ipairs({ "vehicle", "ped" }) do
        for _, element in ipairs(getElementsByType(kind)) do
            if isElement(element) then
                local x, y, z = getElementPosition(element)
                if x >= x0 and x <= x1 and y >= y0 and y <= y1 and z >= z0 and z <= z1 then
                    if destroyElement(element) then
                        removed = removed + 1
                    end
                end
            end
        end
    end
    return removed
end

addCommandHandler("ncempty", function(player, commandName, mode)
    if not isAllowed(player) then
        deny(player)
        return
    end
    mode = string.lower(tostring(mode or ""))
    if mode == "now" then
        local removed = emptyCity(cityAnchors[player])
        tell(player, "removed " .. removed .. " vehicle(s)/ped(s) from the city area.")
    elseif mode == "on" then
        if emptyTimer and isTimer(emptyTimer) then
            tell(player, "automatic city cleanup is already on.")
            return
        end
        emptyTimer = setTimer(function()
            emptyCity({ x = 0, y = 0, z = 900 })
        end, 1000, 0)
        tell(player, "automatic city cleanup is on.")
    elseif mode == "off" then
        if emptyTimer and isTimer(emptyTimer) then
            killTimer(emptyTimer)
        end
        emptyTimer = nil
        tell(player, "automatic city cleanup is off.")
    else
        tell(player, "usage: /ncempty now|on|off")
    end
end)

addEventHandler("onResourceStop", resourceRoot, function()
    if emptyTimer and isTimer(emptyTimer) then
        killTimer(emptyTimer)
    end
    emptyTimer = nil
    for _, player in ipairs(getElementsByType("player")) do
        sendHide(player)
    end
    cityAnchors = {}
end)

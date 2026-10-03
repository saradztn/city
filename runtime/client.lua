-- NightCity client runtime.  The city is streamed as client-side custom models
-- so the original San Andreas world remains intact underneath it.

local modelIds = {}
local modelElements = {}
local txdCache = {}
local allocatedIds = {}
local modelLoadTimer = nil
local loadGeneration = 0
local loadIndex = 0
local loadingModels = false
local modelsReady = false
local cityVisible = false
local worldModified = false
local savedWeather, savedRainLevel = nil, nil
local verticalOffset = 0
local cityAnchorX, cityAnchorY, cityAnchorZ = 0, 0, 900
local cityObjects, cityWater, citySounds = {}, {}, {}
local ambienceTimer, groundProbeTimer, safetyTimer = nil, nil, nil
local groundProbeStart, groundProbeReason = 0, "show"
local playerHeldByCity = false
local wantedRain = 0.0
local rainOverride = false
local fxMode = 1
local wetShader, screenSource = nil, nil
local appliedWetTextures = {}
local glowTexture, steamTexture = nil, nil
local glowSpritesDrawn = 0
local rainSound, humSound, windSound, buzzSound, steamSound, dripSound = nil, nil, nil, nil, nil, nil
local updateAmbience, beginGroundProbe, updateWetScreen

-- Defined here so client.lua can be loaded before tour.lua.
NC_StopTour = nil
NC_StopFreeCamera = nil
function NC_GetCityAnchor()
    return cityAnchorX, cityAnchorY, cityAnchorZ, verticalOffset
end
function NC_IsCityVisible()
    return cityVisible
end

local WET_TEXTURES = {
    "nc_alley", "nc_asphalt", "nc_concrete", "nc_grass", "nc_plaza",
    "nc_road_ave", "nc_road_local", "nc_road_str", "nc_sidewalk"
}

local function say(text)
    outputChatBox("[NightCity] " .. tostring(text), 120, 220, 255, true)
end

local function safeDestroy(element)
    if isElement(element) then
        destroyElement(element)
    end
end

local function cancelTimer(timer)
    if timer and isTimer(timer) then
        killTimer(timer)
    end
end

local function releaseModelAssets(freeIds)
    for _, element in ipairs(modelElements) do
        safeDestroy(element)
    end
    for _, element in pairs(txdCache) do
        safeDestroy(element)
    end
    modelElements, txdCache = {}, {}
    if freeIds then
        for _, id in ipairs(allocatedIds) do
            engineFreeModel(id)
        end
        modelIds, allocatedIds = {}, {}
        modelsReady = false
    end
end

local function abortModelLoad(reason)
    cancelTimer(modelLoadTimer)
    modelLoadTimer = nil
    loadingModels = false
    loadGeneration = loadGeneration + 1
    releaseModelAssets(true)
    if playerHeldByCity then
        setElementFrozen(localPlayer, false)
        playerHeldByCity = false
    end
    say(tostring(reason) .. ". The partial model load was cleaned up.")
end

local function loadOneModel(index)
    local data = NC_MODELS[index]
    if not data then
        return false, "model metadata"
    end
    local id = engineRequestModel("object")
    if not id then
        return false, "engineRequestModel"
    end
    modelIds[index] = id
    table.insert(allocatedIds, id)

    -- MTA requires replacements in COL -> TXD -> DFF order; reversing this can reject DFFs.
    local col = engineLoadCOL("files/" .. data.name .. ".col")
    if not isElement(col) then
        return false, "engineLoadCOL", id
    end
    table.insert(modelElements, col)
    if not engineReplaceCOL(col, id) then
        return false, "engineReplaceCOL", id
    end

    local txd = txdCache[data.txd]
    if not isElement(txd) then
        txd = engineLoadTXD("files/" .. data.txd .. ".txd")
        if not isElement(txd) then
            return false, "engineLoadTXD", id
        end
        txdCache[data.txd] = txd
    end
    if not engineImportTXD(txd, id) then
        return false, "engineImportTXD", id
    end

    local dff = engineLoadDFF("files/" .. data.name .. ".dff")
    if not isElement(dff) then
        return false, "engineLoadDFF", id
    end
    table.insert(modelElements, dff)
    if not engineReplaceModel(dff, id, false) then
        return false, "engineReplaceModel", id
    end
    engineSetModelLODDistance(id, tonumber(data.dist) or 500)
    return true
end

local function registerCityEvents()
    addEvent("nc:show", true)
    addEvent("nc:hide", true)
    addEvent("nc:z", true)
end

local function setCityWorld()
    worldModified = true
    -- Keep MTA's live game clock, weather and timecycle. Forcing noon and a fixed sky
    -- prevents night from appearing and also overwrites server/map time settings.
    savedWeather = getWeather()
    savedRainLevel = getRainLevel()
    if not rainOverride then
        wantedRain = math.max(0, math.min(1, tonumber(savedRainLevel) or 0))
    end
    setRainLevel(wantedRain)
    setFogDistance(380)
    setFarClipDistance(1200)
    setWindVelocity(0.02, 0.01, 0.0)
    setOcclusionsEnabled(false)
    setWaterColor(60, 138, 168, 190)
end

local function restoreCityWorld()
    if not worldModified then
        return
    end
    if savedWeather ~= nil then
        setWeather(savedWeather)
    end
    if savedRainLevel ~= nil then
        setRainLevel(savedRainLevel)
        wantedRain = math.max(0, math.min(1, tonumber(savedRainLevel) or 0))
    else
        resetRainLevel()
        wantedRain = 0.0
    end
    rainOverride = false
    resetFogDistance()
    resetFarClipDistance()
    resetWindVelocity()
    resetHeatHaze()
    resetSunSize()
    resetWaterColor()
    setOcclusionsEnabled(true)
    savedWeather, savedRainLevel = nil, nil
    worldModified = false
end

local function destroyFX()
    if isElement(wetShader) then
        for _, textureName in ipairs(appliedWetTextures) do
            engineRemoveShaderFromWorldTexture(wetShader, textureName)
        end
        safeDestroy(wetShader)
    end
    if isElement(screenSource) then
        removeEventHandler("onClientRender", root, updateWetScreen)
        safeDestroy(screenSource)
    end
    wetShader, screenSource = nil, nil
    appliedWetTextures = {}
end

local function insideTunnel(x, y)
    if not NC_TUNNEL then
        return false
    end
    local tx = cityAnchorX + NC_TUNNEL.x
    local y0 = cityAnchorY + NC_TUNNEL.cov0
    local y1 = cityAnchorY + NC_TUNNEL.cov1
    return math.abs(x - tx) <= (tonumber(NC_TUNNEL.hw) or 7.0) and y >= y0 and y <= y1
end

local function currentWetLevel()
    local x, y = getElementPosition(localPlayer)
    return wantedRain * (insideTunnel(x, y) and 0.25 or 1.0)
end

local function updateWetShader()
    if not isElement(wetShader) then
        return
    end
    local wet = currentWetLevel()
    dxSetShaderValue(wetShader, "gWet", wet)
    dxSetShaderValue(wetShader, "gScreen", screenSource)
    dxSetShaderValue(wetShader, "gTun", cityAnchorX + NC_TUNNEL.x,
                     cityAnchorY + NC_TUNNEL.cov0, cityAnchorY + NC_TUNNEL.cov1,
                     cityAnchorZ + NC_TUNNEL.zf + verticalOffset)
end

updateWetScreen = function()
    if cityVisible and isElement(screenSource) then
        dxUpdateScreenSource(screenSource, true)
    end
end

local function createWetFX()
    if isElement(wetShader) and isElement(screenSource) then
        return true
    end
    local shader, technique = dxCreateShader("wet.fx")
    if not isElement(shader) or technique == "fallback" then
        safeDestroy(shader)
        return false
    end
    local width, height = guiGetScreenSize()
    local source = dxCreateScreenSource(math.max(1, width), math.max(1, height))
    if not isElement(source) or not dxSetShaderValue(shader, "gScreen", source) then
        safeDestroy(shader)
        safeDestroy(source)
        return false
    end
    wetShader, screenSource = shader, source
    appliedWetTextures = {}
    dxSetShaderValue(wetShader, "gWet", currentWetLevel())
    dxSetShaderValue(wetShader, "gTun", cityAnchorX + NC_TUNNEL.x,
                     cityAnchorY + NC_TUNNEL.cov0, cityAnchorY + NC_TUNNEL.cov1,
                     cityAnchorZ + NC_TUNNEL.zf + verticalOffset)
    for _, textureName in ipairs(WET_TEXTURES) do
        if engineApplyShaderToWorldTexture(wetShader, textureName) then
            table.insert(appliedWetTextures, textureName)
        end
    end
    if #appliedWetTextures == 0 then
        destroyFX()
        return false
    end
    addEventHandler("onClientRender", root, updateWetScreen)
    return true
end

local function setFXMode(requested, quiet)
    requested = math.max(0, math.min(1, math.floor(tonumber(requested) or 0)))
    if requested == 0 then
        destroyFX()
        fxMode = 0
        return true
    end
    if not createWetFX() then
        destroyFX()
        fxMode = 0
        if not quiet then
            say("wet.fx could not compile or create; the city remains fully playable without the rain sheen.")
        end
        return false
    end
    updateWetShader()
    fxMode = 1
    return true
end

local function destroyCityFXSprites()
    destroyFX()
    safeDestroy(glowTexture)
    safeDestroy(steamTexture)
    glowTexture, steamTexture = nil, nil
    removeEventHandler("onClientRender", root, drawCitySprites)
end

function drawCitySprites()
    if not cityVisible then
        return
    end
    if not isElement(glowTexture) and not isElement(steamTexture) then
        return
    end
    local cx, cy, cz = getCameraMatrix()
    local drawn, glowDrawn = 0, 0
    local cap = 320
    for i = 1, #NC_SPRITES do
        if drawn >= cap then
            break
        end
        local s = NC_SPRITES[i]
        local x, y, z = cityAnchorX + s[1], cityAnchorY + s[2], cityAnchorZ + s[3] + verticalOffset
        local dx, dy, dz = x - cx, y - cy, z - cz
        if dx * dx + dy * dy + dz * dz < 520 * 520 then
            local kind = tonumber(s[8]) or 1
            local texture = (kind == 1) and glowTexture or steamTexture
            if isElement(texture) then
                local size = math.max(0.25, tonumber(s[4]) or 1.0)
                local red = math.floor(math.max(0, math.min(1, tonumber(s[5]) or 1)) * 255)
                local green = math.floor(math.max(0, math.min(1, tonumber(s[6]) or 1)) * 255)
                local blue = math.floor(math.max(0, math.min(1, tonumber(s[7]) or 1)) * 255)
                dxDrawMaterialLine3D(x, y, z, x, y, z + size, texture, size,
                                     tocolor(red, green, blue, 220), false)
                drawn = drawn + 1
                if kind == 1 then
                    glowDrawn = glowDrawn + 1
                end
            end
        end
    end
    glowSpritesDrawn = glowDrawn
end

local function createCityObjects()
    for _, object in ipairs(cityObjects) do
        safeDestroy(object)
    end
    cityObjects = {}
    for _, water in ipairs(cityWater) do
        safeDestroy(water)
    end
    cityWater = {}

    for _, row in ipairs(NC_OBJECTS) do
        local modelIndex = tonumber(row[1])
        local id = modelIds[modelIndex]
        local x = cityAnchorX + tonumber(row[2])
        local y = cityAnchorY + tonumber(row[3])
        local z = cityAnchorZ + tonumber(row[4]) + verticalOffset
        local rz = tonumber(row[5]) or 0
        local data = NC_MODELS[modelIndex]
        if id and data then
            -- The final createObject flag means isLowLOD; low-LOD elements have no collision in MTA.
            local object = createObject(id, x, y, z, 0, 0, rz, false)
            if isElement(object) then
                setElementFrozen(object, true)
                setElementCollisionsEnabled(object, data.col ~= false)
                table.insert(cityObjects, object)
            end
        end
    end
    for _, water in ipairs(NC_WATER) do
        local x0, y0, x1, y1, z = water[1], water[2], water[3], water[4], water[5]
        local function waterGrid(value)
            return math.floor(value / 2 + 0.5) * 2
        end
        local wx0, wx1 = waterGrid(cityAnchorX + x0), waterGrid(cityAnchorX + x1)
        local wy0, wy1 = waterGrid(cityAnchorY + y0), waterGrid(cityAnchorY + y1)
        local wz = cityAnchorZ + z + verticalOffset
        local element = createWater(wx0, wy0, wz, wx1, wy0, wz, wx0, wy1, wz, wx1, wy1, wz)
        if isElement(element) then
            table.insert(cityWater, element)
        end
    end
    cityVisible = true
    setCityWorld()

    glowTexture = dxCreateTexture("files/fx/glow.png")
    steamTexture = dxCreateTexture("files/fx/steam.png")
    addEventHandler("onClientRender", root, drawCitySprites)

    rainSound = playSound("files/audio/rain_loop.wav", true)
    humSound = playSound("files/audio/hum_loop.wav", true)
    windSound = playSound("files/audio/wind_loop.wav", true)
    buzzSound = playSound("files/audio/buzz_loop.wav", true)
    steamSound = playSound("files/audio/steam_loop.wav", true)
    dripSound = playSound("files/audio/drip_loop.wav", true)
    citySounds = { rainSound, humSound, windSound, buzzSound, steamSound, dripSound }
    for _, sound in ipairs(citySounds) do
        if isElement(sound) then
            setSoundVolume(sound, 0)
        end
    end

    fxMode = 1
    setFXMode(1, true)
    updateWetShader()
    if ambienceTimer and isTimer(ambienceTimer) then
        killTimer(ambienceTimer)
    end
    ambienceTimer = setTimer(updateAmbience, 250, 0)
    updateAmbience()

    local spawn = NC_POINTS.spawn
    setElementVelocity(localPlayer, 0, 0, 0)
    setElementPosition(localPlayer, cityAnchorX + spawn[1], cityAnchorY + spawn[2], cityAnchorZ + spawn[3] + 1.5)
    setCameraTarget(localPlayer)
    beginGroundProbe("show")
    say("city ready: " .. #cityObjects .. " objects. Use /nctour for the skyline and tunnel route.")
end

local function beginModelLoad()
    loadingModels = true
    loadIndex = 0
    loadGeneration = loadGeneration + 1
    local generation = loadGeneration
    modelLoadTimer = setTimer(function()
        if not loadingModels or generation ~= loadGeneration then
            return
        end
        loadIndex = loadIndex + 1
        local loaded, stage, failedId = loadOneModel(loadIndex)
        if not loaded then
            local data = NC_MODELS[loadIndex]
            local detail = string.format("Model %d/%d (%s) failed at %s", loadIndex, #NC_MODELS,
                data and data.name or "unknown", stage or "unknown stage")
            if failedId then
                detail = detail .. " (model ID " .. tostring(failedId) .. ")"
            end
            abortModelLoad(detail)
            return
        end
        if loadIndex >= #NC_MODELS then
            cancelTimer(modelLoadTimer)
            modelLoadTimer = nil
            loadingModels = false
            modelsReady = true
            if playerHeldByCity then
                createCityObjects()
            end
        end
    end, 50, 0)
end

local function cancelPartialLoad()
    if modelLoadTimer and isTimer(modelLoadTimer) then
        killTimer(modelLoadTimer)
    end
    modelLoadTimer = nil
    loadingModels = false
    loadGeneration = loadGeneration + 1
    if not modelsReady and #allocatedIds > 0 then
        releaseModelAssets(true)
    end
end

beginGroundProbe = function(reason)
    cancelTimer(groundProbeTimer)
    groundProbeTimer = nil
    groundProbeReason = reason
    groundProbeStart = getTickCount()
    groundProbeTimer = setTimer(function()
        if not playerHeldByCity or not isElement(localPlayer) then
            cancelTimer(groundProbeTimer)
            groundProbeTimer = nil
            return
        end
        local x, y, z = getElementPosition(localPlayer)
        local hit = processLineOfSight(x, y, z + 8, x, y, z - 120)
        if hit then
            setElementFrozen(localPlayer, false)
            playerHeldByCity = false
            cancelTimer(groundProbeTimer)
            groundProbeTimer = nil
            return
        end
        if getTickCount() - groundProbeStart > 12000 then
            cancelTimer(groundProbeTimer)
            groundProbeTimer = nil
            if groundProbeReason == "view" then
                say("destination not available here yet; stay frozen until you hide the city.")
            else
                say("ground collision is not ready; stay frozen for safety, or use /nchide.")
            end
        end
    end, 300, 0)
end

local function cleanCityElements(restoreWorld)
    cancelTimer(groundProbeTimer)
    groundProbeTimer = nil
    cancelTimer(ambienceTimer)
    ambienceTimer = nil
    destroyCityFXSprites()
    for _, object in ipairs(cityObjects) do
        safeDestroy(object)
    end
    cityObjects = {}
    for _, water in ipairs(cityWater) do
        safeDestroy(water)
    end
    cityWater = {}
    for _, sound in ipairs(citySounds) do
        safeDestroy(sound)
    end
    citySounds = {}
    rainSound, humSound, windSound, buzzSound, steamSound, dripSound = nil, nil, nil, nil, nil, nil
    cityVisible = false
    glowSpritesDrawn = 0
    if restoreWorld then
        restoreCityWorld()
    end
end

local function hideCity(resourceStop)
    local wasLoading = loadingModels
    local hadCity = cityVisible or worldModified
    cancelPartialLoad()
    if NC_StopTour then
        NC_StopTour(false)
    end
    if NC_StopFreeCamera then
        NC_StopFreeCamera(true)
    end
    if cityVisible or worldModified then
        cleanCityElements(true)
    else
        destroyCityFXSprites()
        cancelTimer(groundProbeTimer)
        groundProbeTimer = nil
    end
    if playerHeldByCity then
        setElementFrozen(localPlayer, false)
        playerHeldByCity = false
    end
    if hadCity then
        local _, _, z = getElementPosition(localPlayer)
        if z > 100 then
            setElementVelocity(localPlayer, 0, 0, 0)
            setElementPosition(localPlayer, 2495, -1660, 14)
            setCameraTarget(localPlayer)
        end
    end
    if resourceStop then
        releaseModelAssets(true)
        cancelTimer(safetyTimer)
        safetyTimer = nil
    elseif wasLoading and not modelsReady then
        -- A cancelled partial load was freed above; the next /ncshow starts cleanly.
        modelsReady = false
    end
    verticalOffset = 0
    fxMode = 1
end

local function showCity(x, y, z)
    x, y, z = tonumber(x) or 0, tonumber(y) or 0, tonumber(z) or 900
    if loadingModels then
        cancelPartialLoad()
    end
    if cityVisible then
        cleanCityElements(true)
    end
    cityAnchorX, cityAnchorY, cityAnchorZ = x, y, z
    verticalOffset = 0
    setElementVelocity(localPlayer, 0, 0, 0)
    setElementFrozen(localPlayer, true)
    playerHeldByCity = true
    if modelsReady then
        createCityObjects()
    else
        beginModelLoad()
    end
end

updateAmbience = function()
    if not cityVisible then
        return
    end
    local x, y = getElementPosition(localPlayer)
    local indoors = insideTunnel(x, y)
    local outsideRain = indoors and 0 or wantedRain
    setRainLevel(outsideRain)
    if isElement(rainSound) then
        setSoundVolume(rainSound, math.max(0, math.min(1, outsideRain * 0.72)))
    end
    if isElement(humSound) then
        setSoundVolume(humSound, indoors and 0.72 or 0.06)
    end
    if isElement(windSound) then
        setSoundVolume(windSound, indoors and 0.05 or 0.20)
    end
    if isElement(buzzSound) then
        setSoundVolume(buzzSound, 0.12)
    end
    if isElement(steamSound) then
        setSoundVolume(steamSound, 0.08)
    end
    if isElement(dripSound) then
        setSoundVolume(dripSound, indoors and 0.22 or 0.04)
    end
    updateWetShader()
end

local function usagePoints()
    local names = {}
    for name in pairs(NC_POINTS) do
        table.insert(names, name)
    end
    table.sort(names)
    return table.concat(names, ", ")
end

local function viewPoint(name)
    local point = NC_POINTS[tostring(name or "")]
    if not point then
        say("usage: /ncview <point>. Points: " .. usagePoints())
        return
    end
    if not cityVisible then
        say("city is not shown; use /ncshow first.")
        return
    end
    if NC_StopTour then
        NC_StopTour(false)
    end
    if NC_StopFreeCamera then
        NC_StopFreeCamera(false)
    end
    setElementFrozen(localPlayer, true)
    playerHeldByCity = true
    setElementVelocity(localPlayer, 0, 0, 0)
    setElementPosition(localPlayer, cityAnchorX + point[1], cityAnchorY + point[2], cityAnchorZ + point[3] + 0.5 + verticalOffset)
    setCameraTarget(localPlayer)
    beginGroundProbe("view")
end

local function commandFX(_, value)
    if not cityVisible then
        say("show the city first with /ncshow.")
        return
    end
    local requested
    if value == nil then
        requested = (fxMode + 1) % 2
    else
        requested = tonumber(value)
        if not requested or requested < 0 or requested > 1 then
            say("usage: /ncfx [0|1]")
            return
        end
    end
    local ok = setFXMode(requested, false)
    if ok then
        if fxMode == 1 then
            say("wet-road reflections on; use /ncrain 0.6 for visible rain sheen.")
        else
            say("wet-road reflections off.")
        end
    end
end

local function commandRain(_, value)
    local amount = tonumber(value)
    if not amount then
        say("usage: /ncrain <0..1>")
        return
    end
    wantedRain = math.max(0, math.min(1, amount))
    rainOverride = true
    setWeather(wantedRain > 0 and 8 or 0)
    updateAmbience()
    say("rain set to " .. string.format("%.2f", wantedRain) .. ".")
end

local function commandTime(_, value)
    local hour = tonumber(value)
    if not hour then
        say("usage: /nctime <0..23>")
        return
    end
    hour = math.max(0, math.min(23, math.floor(hour)))
    setTime(hour, 30)
    say("city time set to " .. string.format("%02d:30", hour) .. ".")
end

local function commandInfo()
    say("objects=" .. #cityObjects .. "/" .. #NC_OBJECTS .. "; models=" .. #NC_MODELS ..
        "; glow sprites drawn=" .. glowSpritesDrawn .. "; rain=" .. string.format("%.2f", wantedRain) ..
        "; fx=" .. fxMode .. ".")
end

registerCityEvents()
addEventHandler("nc:show", resourceRoot, function(x, y, z)
    showCity(x, y, z)
end)
addEventHandler("nc:hide", resourceRoot, function()
    hideCity(false)
end)
addEventHandler("nc:z", resourceRoot, function(dz)
    dz = tonumber(dz) or 0
    verticalOffset = verticalOffset + dz
    for _, object in ipairs(cityObjects) do
        if isElement(object) then
            local x, y, z = getElementPosition(object)
            setElementPosition(object, x, y, z + dz)
        end
    end
    for _, water in ipairs(cityWater) do
        if isElement(water) then
            local _, z = getElementPosition(water)
            setWaterLevel(water, z + dz)
        end
    end
    updateWetShader()
end)

addCommandHandler("ncfx", commandFX)
addCommandHandler("ncrain", commandRain)
addCommandHandler("nctime", commandTime)
addCommandHandler("ncview", function(_, point) viewPoint(point) end)
addCommandHandler("ncinfo", commandInfo)

addEventHandler("onClientResourceStart", resourceRoot, function()
    wantedRain = math.max(0, math.min(1, tonumber(getRainLevel()) or 0))
    if not safetyTimer or not isTimer(safetyTimer) then
        safetyTimer = setTimer(function()
            if playerHeldByCity and not groundProbeTimer then
                setElementFrozen(localPlayer, true)
            end
        end, 5000, 0)
    end
    triggerServerEvent("nc:ready", resourceRoot)
end)

addEventHandler("onClientResourceStop", resourceRoot, function()
    hideCity(true)
end)

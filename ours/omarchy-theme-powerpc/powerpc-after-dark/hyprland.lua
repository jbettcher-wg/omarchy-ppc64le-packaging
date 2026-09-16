local active_border_color = { colors = { "rgba(C3325Aee)", "rgba(BE9E64ee)" }, angle = 45 }
local inactive_border_color = "rgba(3A2C1Ecc)"
local active_shadow_color = "rgba(00000070)"
local inactive_shadow_color = "rgba(00000030)"

hl.config({
  general = {
    border_size = 2,
    gaps_in = 5,
    gaps_out = 10,
    col = {
      active_border = active_border_color,
      inactive_border = inactive_border_color,
    },
  },

  group = {
    col = {
      border_active = active_border_color,
      border_inactive = inactive_border_color,
    },
  },

  decoration = {
    rounding = 8,
    shadow = {
      enabled = true,
      range = 22,
      render_power = 3,
      color = active_shadow_color,
      color_inactive = inactive_shadow_color,
    },
    blur = {
      enabled = false,
    },
  },
})

hl.curve("jacketEase", { type = "bezier", points = { { 0.22, 0.08 }, { 0.2, 1 } } })
hl.animation({ leaf = "border", enabled = true, speed = 8, bezier = "jacketEase" })
hl.animation({ leaf = "windowsIn", enabled = true, speed = 7, bezier = "jacketEase", style = "popin 80%" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 5, bezier = "jacketEase", style = "slide" })

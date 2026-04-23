(function (global) {
  "use strict";

  function toNumber(value) {
    var parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function esc(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function render(targetId, payload, options) {
    var root = document.getElementById(targetId);
    if (!root || !payload) {
      return;
    }

    var wname = payload.wname || "All Weapons";
    var head = toNumber(payload.head);
    var leftarm = toNumber(payload.leftarm);
    var rightarm = toNumber(payload.rightarm);
    var chest = toNumber(payload.chest);
    var stomach = toNumber(payload.stomach);
    var leftleg = toNumber(payload.leftleg);
    var rightleg = toNumber(payload.rightleg);
    var model = payload.model || "ct";

    var textColor = (options && options.textcolor) || "#FFFFFF";
    var captionColor = (options && options.captioncolor) || "#FFFFFF";
    var numberColor = (options && options.numcolor_num) || "#FFFFFF";
    var percentColor = (options && options.numcolor_pct) || "#FFFFFF";
    var barColor = (options && options.barcolor) || "#FFFFFF";
    var barBackground = (options && options.barbackground) || "#000000";
    var lineColor = (options && options.linecolor) || "#FFFFFF";
    var textColorTotal = (options && options.textcolor_total) || "#FFFFFF";
    var imageBase = (options && options.imageBase) || "hlstatsimg";

    var total = head + leftarm + rightarm + chest + stomach + leftleg + rightleg;
    var scale = 20;
    var largest = Math.max(head, leftarm, rightarm, chest, stomach, leftleg, rightleg);
    var scaleVal = largest > 0 ? scale / largest : 0;
    var graphScale = total > 0 ? scale / total : 0;

    function pct(value) {
      if (!total) {
        return "0%";
      }
      return String(Math.round((value / total) * 100)) + "%";
    }

    function frame(value) {
      return Math.round(value * scaleVal);
    }

    function graph(value) {
      return Math.round(value * graphScale);
    }

    // Flash used swapped left/right bars intentionally; mirror that behavior.
    var rows = [
      { label: "Total Hits", value: total, percent: "", graph: frame(total) },
      { label: "Head", value: head, percent: pct(head), graph: graph(head) },
      { label: "Left Arm", value: leftarm, percent: pct(leftarm), graph: graph(rightarm) },
      { label: "Right Arm", value: rightarm, percent: pct(rightarm), graph: graph(leftarm) },
      { label: "Chest", value: chest, percent: pct(chest), graph: graph(chest) },
      { label: "Stomach", value: stomach, percent: pct(stomach), graph: graph(stomach) },
      { label: "Left Leg", value: leftleg, percent: pct(leftleg), graph: graph(rightleg) },
      { label: "Right Leg", value: rightleg, percent: pct(rightleg), graph: graph(leftleg) },
    ];

    var rowHtml = rows
      .map(function (row, index) {
        var width = Math.max(0, Math.min(20, row.graph)) * 6;
        var valueColor = index === 0 ? textColorTotal : numberColor;
        var percentCell = row.percent
          ? '<span style="color:' + esc(percentColor) + ';">' + esc(row.percent) + "</span>"
          : "";
        return (
          '<tr>' +
          '<td style="color:' + esc(textColor) + ';padding:2px 4px;">' + esc(row.label) + "</td>" +
          '<td style="padding:2px 4px;"><div style="width:120px;height:10px;border:1px solid ' +
          esc(lineColor) +
          ";background:" +
          esc(barBackground) +
          ';"><div style="height:100%;width:' +
          width +
          "px;background:" +
          esc(barColor) +
          ';"></div></div></td>' +
          '<td style="color:' +
          esc(valueColor) +
          ';padding:2px 4px;text-align:right;">' +
          esc(row.value) +
          "</td>" +
          '<td style="padding:2px 4px;text-align:right;">' +
          percentCell +
          "</td>" +
          "</tr>"
        );
      })
      .join("");

    var modelPath = imageBase + "/hitbox_models/" + model + ".png";
    root.innerHTML =
      '<div style="padding:8px 10px;">' +
      '<div style="font-weight:bold;color:' +
      esc(captionColor) +
      ';margin-bottom:6px;">' +
      esc(wname) +
      "</div>" +
      '<div style="display:flex;gap:10px;align-items:flex-start;justify-content:center;">' +
      '<div style="width:200px;height:300px;border:1px solid ' +
      esc(lineColor) +
      ';background:#000;display:flex;align-items:center;justify-content:center;overflow:hidden;">' +
      '<img src="' +
      esc(modelPath) +
      '" alt="' +
      esc(model) +
      '" style="max-width:100%;max-height:100%;" onerror="this.style.display=\'none\'" />' +
      "</div>" +
      '<table style="border-collapse:collapse;font-size:11px;line-height:1.2;">' +
      rowHtml +
      "</table>" +
      "</div>" +
      "</div>";
  }

  global.HLXHitboxModern = {
    render: render,
  };
})(window);

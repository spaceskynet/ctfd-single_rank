if($ === undefined) $ = CTFd.lib.$;
const graph = $("#score-graph");

function htmlentities(string) {
  return $("<div/>")
    .text(string)
    .html();
}

function getCategoryFromRequest() {
  var urlParams = new URLSearchParams(window.location.search);
  var category = urlParams.get('category');
  return category;
}

function updatescoresByCategory() {
  var category = getCategoryFromRequest();
  if (category === null) {
    category = "All";
  }
  const target = '/scoreboard/top?category=' + category;
  $.get(target, function(response) {
    var teams = response.data;
    var table = $("#scoreboard tbody");
    table.empty();
    for (var i = 0; i < teams.length; i++) {
      var oauth_html = '';
      if(teams[i].oauth_id){
        if(CTFd.config.userMode == 'teams'){
          oauth_html = '<a href="https://majorleaguecyber.org/t/{0}">\n<span class="badge badge-primary">Official</span>\n</a>'.format(teams[i].oauth_id)
        }
        else if(CTFd.config.userMode == 'users') {
          oauth_html = '<a href="https://majorleaguecyber.org/u/{0}">\n<span class="badge badge-primary">Official</span>\n</a>'.format(teams[i].oauth_id)
        }
      }
      const date = Moment(teams[i].last_point_time)
        .local()
        .fromNow();
      var row =
        "<tr>\n" +
        '<th scope="row" class="text-center">{0}</th>'.format(teams[i].pos) +
        '<td><a href="{0}">{1}{2}</a></td>'.format(
          teams[i].account_url,
          htmlentities(teams[i].name),
          oauth_html
        ) +
        "<td>{0}</td>".format(teams[i].scores) +
        "<td>{0}</td>".format(teams[i].solves) +
        "<td>{0}</td>".format(date) +
        "</tr>";
      table.append(row);
    }
  });
}

function cumulativeSum(arr) {
  var result = arr.concat();
  for (var i = 0; i < arr.length; i++) {
    result[i] = arr.slice(0, i + 1).reduce(function(p, i) {
      return p + i;
    });
  }
  return result;
}

function colorHash(str) {
  var hash = 0;
  for (var i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  var colour = "#";
  for (var i = 0; i < 3; i++) {
    var value = (hash >> (i * 8)) & 0xff;
    colour += ("00" + value.toString(16)).substr(-2);
  }
  return colour;
}

function UTCtoDate(utc) {
  var d = new Date(0);
  d.setUTCSeconds(utc);
  return d;
}

const buildGraphData = function(){
  var category = getCategoryFromRequest();
  if (category === null) {
    category = "All";
  }

  const target = '/scoreboard/top/10?category=' + category;
  return $.get(target).then(response => {
    const places = response.data;

    const teams = Object.keys(places);
    if (teams.length === 0) {
      return false;
    }

    const option = {
      title: {
        left: "center",
        text: "Top 10 " + (CTFd.config.userMode === "teams" ? "Teams" : "Users")
      },
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "cross"
        }
      },
      legend: {
        type: "scroll",
        orient: "horizontal",
        align: "left",
        bottom: 35,
        data: []
      },
      toolbox: {
        feature: {
          dataZoom: {
            yAxisIndex: "none"
          },
          saveAsImage: {}
        }
      },
      grid: {
        containLabel: true
      },
      xAxis: [
        {
          type: "time",
          boundaryGap: false,
          data: []
        }
      ],
      yAxis: [
        {
          type: "value"
        }
      ],
      dataZoom: [
        {
          id: "dataZoomX",
          type: "slider",
          xAxisIndex: [0],
          filterMode: "filter"
        }
      ],
      series: []
    };

    for (let i = 0; i < teams.length; i++) {
      const team_score = [];
      const times = [];
      for (let j = 0; j < places[teams[i]]["solves"].length; j++) {
        team_score.push(places[teams[i]]["solves"][j].value);
        const date = Moment(places[teams[i]]["solves"][j].date);
        times.push(date.toDate());
      }

      const total_scores = cumulativeSum(team_score);
      var scores = times.map(function(e, i) {
        return [e, total_scores[i]];
      });

      option.legend.data.push(places[teams[i]]["name"]);

      const data = {
        name: places[teams[i]]["name"],
        type: "line",
        label: {
          normal: {
            position: "top"
          }
        },
        itemStyle: {
          normal: {
            color: colorHash(places[teams[i]]["name"] + places[teams[i]]["id"])
          }
        },
        data: scores
      };
      option.series.push(data);
    }
    return option;
  });
};

const createGraph = function() {
  buildGraphData().then(option => {
    if (option === false) {
      // Replace spinner
      graph.html(
        '<h3 class="opacity-50 text-center w-100 justify-content-center align-self-center">No solves yet</h3>'
      );
      return;
    }

    graph.empty(); // Remove spinners
    let chart = echarts.init(document.querySelector("#score-graph"));
    chart.setOption(option);

    $(window).on("resize", function() {
      if (chart != null && chart != undefined) {
        chart.resize();
      }
    });
  });
};

const updateGraph = function() {
  buildGraphData().then(option => {
    let chart = echarts.init(document.querySelector("#score-graph"));
    chart.setOption(option);
  });
};

function update() {
  updatescoresByCategory();
  scoregraph();
}

$(() => {
  setInterval(update, 300000); // Update scores every 5 minutes
  createGraph();
  updatescoresByCategory();
});
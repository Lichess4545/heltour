  var chessGrounds = {};
  var ws = null;
  var queue = [];
  
  var shown_games = {};
  var schedule_max = 10;
  var schedule_page_size = 10;

  function send (ws, message) {
    if(ws.readyState === 1) {
      ws.send(message);
    }
    else {
      queue.push(message);
    }
  }

  function run () {
    const baseURL = 'wss://socket.lichess.org';
    const endpoint = '/api/socket';
    const url = baseURL + endpoint;
    ws = new WebSocket(url);

    ws.onopen = function () {
      while(queue.length > 0) {
        var message = queue.pop();
        ws.send(message);
      }
    }

    ws.onerror = function (error) {
      console.error(error);
    }

    ws.onmessage = function (e) {
      const m = JSON.parse(e.data);

      if(m.t === 'fen') {
        var ground = chessGrounds[m.d.id];
        m.d.lastMove = [m.d.lm.substring(0,2), m.d.lm.substring(2,4)];
        ground.set(m.d);
      }
    }
    
    ws.onclose = function() {
    	run();
    	$.each(shown_games, function(id, el) {
    	    var message = JSON.stringify({
    	      t: 'startWatching',
    	      d: id
    	    })
    	    send(ws, message);
    	});
    }
  }

  run();

  function newBoard($parent, game, m) {
    var chess = new Chess();

    var ground = Chessground($parent.find('.chessground')[0], {
      fen: '8/8/8/8/8/8/8/8',
      coordinates: false,
      viewOnly: true,
      turnColor: 'white',
      animation: {
        duration: 500
      },
      movable: {
        free: false,
        color: null,
        premove: true,
        dests: {},
        events: {
          after: null
        }
      },
      drawable: {
        enabled: false
      }
    });

    chessGrounds[game.id] = ground;
    
    if (m) {
	    m.d.lastMove = [m.d.lm.substring(0,2), m.d.lm.substring(2,4)];
	    ground.set(m.d);
    } else {
    	$.ajax({
    	      url:'https://en.lichess.org/api/game/' + game.id,
    	      data: {
    	        with_moves: 1
    	      },
    	      dataType:'jsonp',
    	      jsonp:'callback',
    	      success: function(data) {
    	    	  if (data.moves) {
		              var a = {};
		              const chess = new Chess();
		              data.moves.split(' ').forEach(chess.move);
		              const history = chess.history({verbose: true});
		              const lastMoveObj = history[history.length-1];
		              a.lastMove = [lastMoveObj.from, lastMoveObj.to];
		              a.fen = chess.fen();
		              ground.set(a);
	              }
    	      }
    	});
    }
    
    var top_label = $parent.find('.top-label');
    top_label.find('.player-div').show();
    top_label.find('.player-name').text(game.black_name);
    top_label.find('.player-rating').text(game.black_rating);
    top_label.find('.player-link').attr('href', '/' + game.league + '/season/' + game.season + '/player/' + game.black_name + '/');
    if (game.black_team) {
      top_label.find('.team-div').show();
      top_label.find('.board-number').text(game.board_number);
      top_label.find('.team-name').text(game.black_team.name);
      top_label.find('.team-score').text(game.black_team.score.toFixed(1));
      top_label.find('.team-link').attr('href', '/' + game.league + '/season/' + game.season + '/team/' + game.black_team.number + '/');
    }
    

    var bottom_label = $parent.find('.bottom-label');
    bottom_label.find('.player-div').show();
    bottom_label.find('.player-name').text(game.white_name);
    bottom_label.find('.player-rating').text(game.white_rating);
    bottom_label.find('.player-link').attr('href', '/' + game.league + '/season/' + game.season + '/player/' + game.white_name + '/');
    if (game.white_team) {
      bottom_label.find('.team-div').show();
      bottom_label.find('.board-number').text(game.board_number);
      bottom_label.find('.team-name').text(game.white_team.name);
      bottom_label.find('.team-score').text(game.white_team.score.toFixed(1));
      bottom_label.find('.team-link').attr('href', '/' + game.league + '/season/' + game.season + '/team/' + game.white_team.number + '/');
    }

    var message = JSON.stringify({
      t: 'startWatching',
      d: game.id
    })
    send(ws, message);

  };
  
  function render(data) {
	  // Populate a set of all the games we're about to show
	  var next_games = {};
	  $.each(data.games, function(i, g) {
	  	next_games[g.id] = 1;
	  });
	  var messages = {};
	  $.each(data.watch, function(i, msg) {
		  if (msg) {
			  messages[msg.d.id] = msg;
		  }
	  });
	  
	  // Delete existing games we're not showing any more
	  $('#games-row').children().each(function(i, el) {
	  	var id = $(el).data('id');
	  	if (!(id in next_games)) {
	  		$('#finished-games').show();
	  		$('#finished-games-row').prepend(el);
	  		delete shown_games[id];
	  	}
	  });
	  
	  // Show new games
	  $.each(data.games, function(i, g) {
	  	if (g.id in shown_games) {
	  		var $g = shown_games[g.id];
	  		$g.toggle(g.matches_filter);
	  		if (g.matches_filter && !$g.data('has_board')) {
		  		newBoard($g, g, messages[g.id]);
		  		$g.data('has_board', true);
	  		}
	  	} else {
		  	var $g = $('#game-template').clone().attr('id', null).data('id', g.id);
		  	$g.find('.chessground').wrap('<a href="https://en.lichess.org/' + g.id + '"></a>');
		  	$('#games-row').append($g);
		  	if (g.matches_filter) {
		  		$g.show();
		  		newBoard($g, g, messages[g.id]);
		  		$g.data('has_board', true);
		  	}
		  	shown_games[g.id] = $g;
	  	}
	  });
	  
	  // Render the schedule
	  $('#schedule').empty();
	  var days = [];
	  var day_schedules = [];
	  var count = 0;
	  $.each(data.schedule, function(i, g) {
	  	if (g.matches_filter) {
	  		count++;
	  		if (count > schedule_max) {
	  			return;
	  		}
	  		g.time = moment(g.time);
	  		if ($('#id_timezone').val() === 'utc') {
	  			g.time = g.time.utc();
	  		}
	  		var day = g.time.format('dddd, MMM D');
	  		var index = days.indexOf(day);
	  		if (index === -1) {
	  			days.push(day);
	  			day_schedules.push([]);
	  			index = days.length - 1;
	  		}
  			day_schedules[index].push(g);
	  	}
	  });
	  $('#more-schedule').toggle(count > schedule_max);
	  
	  for (var i = 0; i < days.length; i++) {
	  	var $thead = $('<thead><tr><th colspan="3">' + days[i] + '</th><th>Time</th></thead>').appendTo('#schedule');
	  	var $tbody = $('<tbody></tbody>').appendTo('#schedule');
	  	for (var j = 0; j < day_schedules[i].length; j++) {
	  		var g = day_schedules[i][j];
	  		$('<tr><td><a href="/' + g.league + '/season/' + g.season + '/player/' + g.white_name + '">' + g.white + '</a></td><td>-</td>' +
	  		  '<td><a href="/' + g.league + '/season/' + g.season + '/player/' + g.black_name + '">' + g.black + '</a></td>' +
	  		  '<td>' + g.time.format('HH:mm') + '</td></tr>').appendTo($tbody);
//	  		if (g.board_number) {
//	  			$('<tr class="team-row"><td><a href="/' + g.league + '/season/' + g.season + '/team/' + g.white_team.number + '">' + g.white_team.name + '</a></td>' +
//                      '<td><a href="/' + g.league + '/season/' + g.season + '/team/' + g.black_team.number + '">' + g.black_team.name + '</a></td><td></td></tr>' +
//                  '<tr class="board-row"><td>Board ' + g.board_number + '</td><td></td><td></td></tr>').appendTo($tbody);
//	  		}
	  	}
	  }
	  
	  $('#no-games').toggle(!data.games.length);
	  $('#no-filter-games').toggle(!!data.games.length && !$('#games-row').children().filter(':visible').length);
	  
	  $('#no-schedule').toggle(!data.schedule.length);
	  $('#no-filter-schedule').toggle(!!data.schedule.length && !$('#schedule').children().length);
  }
  
  function poll() {
  	var hashParts = location.hash.substring(1).split('&');
  	var league = currentLeague;
  	var board = 'all';
  	var team = 'all';
  	var timezone = 'local';
  	$.each(hashParts, function(i, s) {
  		if (s.startsWith('league=')) {
  			league = s.substring('league='.length);
  		} else if (s.startsWith('board=')) {
  			board = s.substring('board='.length);
  		} else if (s.startsWith('team=')) {
  			team = s.substring('team='.length);
  		} else if (s.startsWith('timezone=')) {
  			timezone = s.substring('timezone='.length);
  		}
  	});
  	$('#id_league').val(league);
  	$('#id_board').val(board);
  	$('#id_team').val(team);
  	$('#id_timezone').val(timezone);
  	$.get(jsonUrl + '?league=' + league + '&board=' + board + '&team=' + team, function(data) {
  		render(data);
  	});
  }
  
  function pollSingle() {
  	$.get(jsonUrl + '?league=' + currentLeague+ '&board=all&team=all', function(data) {
  		renderSingle(data);
  	});
  }
  
  var currentGameId = null;
  function renderSingle(data) {
	  var messages = {};
	  $.each(data.watch, function(i, msg) {
		  if (msg) {
			  messages[msg.d.id] = msg;
		  }
	  });
	  for (var i = 0; i < data.games.length; i++) {
		  var g = data.games[i];
		  if (!g.matches_filter) {
			  continue;
		  }
		  $('#single-game-well').toggle(!!g);
		  
		  if (g && g.id !== currentGameId && g.matches_filter) {
			  $('#single-game-container').empty();
			  var $g = $('#game-template').clone().attr('id', null).data('id', g.id);
		      $g.find('.chessground').wrap('<a href="https://en.lichess.org/' + g.id + '"></a>');
			  $('#single-game-container').append($g);
		  	  $g.show();
		  	  newBoard($g, g, messages[g.id]);
		  	  currentGameId = g.id;
		  }
		  break;
	  }
  }
  
  function updateHash() {
  	var hashParts = [];
  	if ($('#id_timezone').length && $('#id_timezone').val() !== 'local') {
  		hashParts.push('timezone=' + $('#id_timezone').val());
  	}
  	if ($('#id_league').val() === 'all') {
  		hashParts.push('league=all');
  	} else if ($('#id_league').val() != currentLeague) {
  		var url = '/' + $('#id_league').val() + '/tv/'
  		if (hashParts.length > 0) {
  			url += "#" + hashParts.join('&');
  		}
  		location.href = url;
  		return;
  	}
  	if ($('#id_board').length && $('#id_board').val() !== 'all') {
  		hashParts.push('board=' + $('#id_board').val());
  	}
  	if ($('#id_team').length && $('#id_team').val() !== 'all') {
  		hashParts.push('team=' + $('#id_team').val());
  	}
  	if (history.pushState) {
  		history.pushState(null, null, hashParts.length ? '#' + hashParts.join('&') : location.pathname);
  		poll();
  	} else {
  		location.hash = hashParts.join('&') || '_';
  	}
  }

  $(function() {
	  $('body').on('click', '.btn-flip-board', function(e) {
		  e.preventDefault();
		  e.stopPropagation();
		  var $c = $(this).closest('.game-container');
		  var id = $c.data('id');
		  var cg = chessGrounds[id];
		  cg.toggleOrientation();
		  $(this).closest('.dropdown').removeClass('open');
	  });
  });
 
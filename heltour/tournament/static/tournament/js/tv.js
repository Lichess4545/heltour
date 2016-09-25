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
    const url = baseURL + endpoint + '?sri=' + Math.random().toString(36).substring(2)
    ws = new WebSocket(url);

    ws.onopen = function () {
      while(queue.length > 0) {
        let message = queue.pop();
        ws.send(message);
      }
    }

    ws.onerror = function (error) {
      console.error(error);
    }

    ws.onmessage = function (e) {
      const m = JSON.parse(e.data);

      if(m.t === 'fen') {
        let ground = chessGrounds[m.d.id];
        m.d.lastMove = [m.d.lm.substring(0,2), m.d.lm.substring(2,4)];
        ground.set(m.d);
      }
    }
    
    ws.onclose = function() {
    	run();
    	$.each(shown_games, function(id, el) {
    	    let message = JSON.stringify({
    	      t: 'startWatching',
    	      d: id
    	    })
    	    send(ws, message);
    	});
    }
  }

  run();

  function newBoard($parent, game) {
    let chess = new Chess();

    let ground = Chessground($parent.find('.chessground')[0], {
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

    $.ajax({
      url:'https://en.lichess.org/api/game/' + game.id,
      data: {
        with_moves: 1
      },
      dataType:'jsonp',
      jsonp:'callback',
      success: function(data) {
        if(data.players) {
          let top_label = null;
          $parent.find('.top-label')
                 .text(data.players.black.userId + ' (' + data.players.black.rating + ')')
                 .wrap('<a href="/' + game.league + '/season/' + game.season + '/player/' + data.players.black.userId + '/"></a>');
          if (game.black_team)
            $parent.find('.top-team-label')
                   .text(game.black_team.name + ' (Board ' + game.board_number + ')')
                   .wrap('<a href="/' + game.league + '/season/' + game.season + '/team/' + game.black_team.number + '/"></a>');
          

          let bottom_label = null;
          $parent.find('.bottom-label')
                 .text(data.players.white.userId + ' (' + data.players.white.rating + ')')
                 .wrap('<a href="/' + game.league + '/season/' + game.season + '/player/' + data.players.white.userId + '/"></a>');
          if (game.white_team)
            $parent.find('.bottom-team-label')
                   .text(game.white_team.name + ' (Board ' + game.board_number + ')')
                   .wrap('<a href="/' + game.league + '/season/' + game.season + '/team/' + game.white_team.number + '/"></a>');
        }

        if (data.moves) {
          let a = {};
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

    let message = JSON.stringify({
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
	  
	  // Delete existing games we're not showing any more
	  $('#games-row').children().each(function(i, el) {
	  	var id = $(el).data('id');
	  	if (!(id in next_games)) {
	  		$('#finished-games').show();
	  		$('#finished-games-row').append(el);
	  		delete shown_games[id];
	  	}
	  });
	  
	  // Show new games
	  $.each(data.games, function(i, g) {
	  	if (g.id in shown_games) {
	  		var $g = shown_games[g.id];
	  		$g.toggle(g.matches_filter);
	  		if (g.matches_filter && !$g.data('has_board')) {
		  		newBoard($g, g);
		  		$g.data('has_board', true);
	  		}
	  	} else {
		  	var $g = $('#game-template').clone().attr('id', null).data('id', g.id);
		  	$g.find('.chessground').wrap('<a href="https://en.lichess.org/' + g.id + '"></a>');
		  	$('#games-row').append($g);
		  	if (g.matches_filter) {
		  		$g.show();
		  		newBoard($g, g);
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
		  	  newBoard($g, g);
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
  	location.hash = hashParts.join('&');
  }

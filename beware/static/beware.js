function checkError(response, status, xhr) {
  if (status == "error") {
    if (xhr.status == 500) {
      $("#reservations-content").html(status + response);
    } else if (xhr.status == 401) {
      // login again
      window.location.replace("index?error=Session%20expired,%20please%20login%20again.");
    } else if (xhr.status == 0) {
      alert("Unknown network error occured.");
    } else if (xhr.status == 418) {
      $("#error-popup-message").html(response);
      $("#error-popup").show();
    } else {
    	// FIXME popup?
    	alert(xhr.status + ": " + response);
    }
  }
}

function bewareLogin(form) {
	var user = form.user.value;
	var password = form.password.value;
	
	jQuery.ajax({
		type: "POST",
		url: "login",
		data: { user: user, password: password },
		success: function (response) {
			window.location.replace("objects");
		},
		error: function (xhr, status, errorThrown) {
			if (xhr.status == 401) {
				$('#loading-indicator').hide();
				$("#error-popup-message").html(xhr.responseText);
				$("#error-popup").show();
			} else {
		    	alert(xhr.status + ": " + xhr.responseText);
			}
		},
	});
	
	return false;
}

function loadReservations(object, timestamp) {
	curObject = object;
	
	url = "reservations?object=" + object;

	if (timestamp >= 0) {
		curTs = timestamp;
		url += "&fromTs=" + timestamp;
	}
	
	$("#reservations-content").load(url, checkError);
}

function checkXhr(xhr, status, errorThrown) {
	// Since make, cancel won't hide on global events..
	$('#loading-indicator').hide();
	
	// jQuery is just trippy..
	return checkError(xhr.responseText, status, xhr);
}

function makeReservation(object, fromTs, toTs) {
    jQuery.ajax({
        type: "GET",
        url: "reserve?object=" + object + "&start=" + fromTs + "&end=" + toTs,
        global: false,
        beforeSend: function(response) {
        	// before, but not after.
        	$('#loading-indicator').show();
        },
        success: function (response) {
        	loadReservations(curObject, curTs);
        },
        error: checkXhr,
      });
}

function cancelReservation(object, fromTs) {
    jQuery.ajax({
        type: "GET",
        url: "cancel?object=" + object + "&start=" + fromTs,
        global: false,
        beforeSend: function(response) {
        	// before, but not after.
        	$('#loading-indicator').show();
        },
        success: function (response) {
        	loadReservations(curObject, curTs);
        },
        error: checkXhr,
      });
}

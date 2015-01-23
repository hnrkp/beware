function checkError(response, status, xhr) {
  if (status == "error") {
    if (xhr.status == 500) {
      $("#reservations-content").html(status + response);
    } else if (xhr.status == 401) {
      // login again
      window.location.href = "/?error=Session%20expired,%20please%20login%20again.";
    } else {
    	// FIXME popup?
    	alert(response);
    }
  }
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
	// jQuery is just trippy..
	return checkError(xhr.responseText, status, xhr);
}

function makeReservation(object, fromTs, toTs) {
    jQuery.ajax({
        type: "GET",
        url: "reserve?object=" + object + "&start=" + fromTs + "&end=" + toTs,
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
        success: function (response) {
        	loadReservations(curObject, curTs);
        },
        error: checkXhr,
      });
}
